import logging
from pathlib import Path
from typing import Any, Dict, Optional
import numpy as np
import scipy.signal
import soundfile as sf

from app.clone.dsp import AudioDSP
from app.clone.profile import CloneManager, CloneProfile
from app.clone.speaker_encoder import SpeakerEncoder
from app.tts.piper_engine import PiperTTSEngine
from app.utils.atomic_audio import validate_wav_file
from app.utils.paths import MODELS_DIR

logger = logging.getLogger(__name__)


class VoiceCloningEngine:
    """100% Offline CPU Voice Cloning Engine combining Piper phonetics with acoustic timbre morphing."""

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = models_dir or MODELS_DIR
        self.clone_manager = CloneManager(self.models_dir / "clones")
        self.speaker_encoder = SpeakerEncoder(self.models_dir / "encoder" / "speaker_encoder.onnx")
        self.piper_engine = PiperTTSEngine()
        self.converter_onnx_path = self.models_dir / "converter" / "converter.onnx"
        self._converter_session = None
        self._init_converter()

    def _init_converter(self):
        if self.converter_onnx_path.is_file():
            try:
                import onnxruntime as ort

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 4
                self._converter_session = ort.InferenceSession(
                    str(self.converter_onnx_path), opts, providers=["CPUExecutionProvider"]
                )
                logger.info("Loaded ONNX Tone Color Converter: %s", self.converter_onnx_path)
            except Exception as e:
                logger.warning("Failed loading ONNX converter, using acoustic formant transfer: %s", e)
                self._converter_session = None

    def synthesize_cloned(
        self,
        text: str,
        clone_id: str,
        output_path: Path,
        speed: float = 1.0,
    ) -> Path:
        """Synthesize text in the exact timbre and pitch profile of a cloned voice."""
        clone = self.clone_manager.get_clone(clone_id)
        if not clone:
            raise KeyError(f"Cloned voice profile '{clone_id}' not found.")

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_base_wav = output_path.with_suffix(".base_tmp.wav")

        try:
            # 1. Resolve base voice model config with model_path and config_path
            from app.tts.voice_manager import list_local_voices
            from app.utils.paths import VOICES_DIR

            voices = {v["key"]: v for v in list_local_voices(include_clones=False)}
            base_voice_cfg = voices.get(clone.base_voice_key)

            if not base_voice_cfg:
                onnx_path = VOICES_DIR / f"{clone.base_voice_key}.onnx"
                json_path = VOICES_DIR / f"{clone.base_voice_key}.onnx.json"
                if onnx_path.is_file():
                    base_voice_cfg = {
                        "key": clone.base_voice_key,
                        "model_path": str(onnx_path),
                        "config_path": str(json_path),
                        "sample_rate": 22050,
                    }
                else:
                    avail = list_local_voices(include_clones=False)
                    if avail:
                        base_voice_cfg = dict(avail[0])
                    else:
                        raise FileNotFoundError(f"No base voice model installed for '{clone.base_voice_key}'")

            base_voice_cfg = dict(base_voice_cfg)
            base_voice_cfg["speed"] = speed * clone.speed_factor

            self.piper_engine.synthesize_to_wav(text, tmp_base_wav, base_voice_cfg)
            validate_wav_file(tmp_base_wav)

            # 2. Load target speaker embedding and spectral envelope
            target_emb = self.clone_manager.load_embedding(clone_id)
            target_env = self.clone_manager.load_spectral_envelope(clone_id)
            effective_pitch_shift = self.clone_manager.get_effective_pitch_shift(clone_id)

            if target_emb is None and target_env is None:
                # Fallback to direct base copy if models are missing
                tmp_base_wav.replace(output_path)
                return output_path

            # 3. Apply Tone Color / Formant Morphing to adopt user's vocal tract resonance
            self.morph_timbre(
                source_wav_path=tmp_base_wav,
                target_embedding=target_emb,
                output_wav_path=output_path,
                pitch_shift_semitones=effective_pitch_shift,
                target_envelope=target_env,
            )

            validate_wav_file(output_path)
            return output_path

        finally:
            if tmp_base_wav.exists():
                tmp_base_wav.unlink()

    def morph_timbre(
        self,
        source_wav_path: Path,
        target_embedding: Optional[np.ndarray],
        output_wav_path: Path,
        pitch_shift_semitones: float = 0.0,
        target_envelope: Optional[np.ndarray] = None,
    ) -> Path:
        """Apply acoustic formant and spectral resonance transfer from target embedding to source speech."""
        audio, sr = sf.read(str(source_wav_path), dtype="float32")
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        # If neural converter is available, evaluate neural graph
        if self._converter_session is not None and target_embedding is not None:
            try:
                inputs = {
                    self._converter_session.get_inputs()[0].name: np.expand_dims(audio, axis=0).astype(np.float32),
                    self._converter_session.get_inputs()[1].name: np.expand_dims(target_embedding, axis=0).astype(np.float32),
                }
                morphed = self._converter_session.run(None, inputs)[0].squeeze()
                sf.write(str(output_wav_path), morphed, sr, subtype="PCM_16")
                return output_wav_path
            except Exception as e:
                logger.warning("Neural converter error, using acoustic formant transfer: %s", e)

        # High-Fidelity Formant & Pitch Transfer DSP
        # 1. Pitch shift using SOLA cross-correlation (zero phase smearing)
        if abs(pitch_shift_semitones) > 0.15:
            audio = AudioDSP.pitch_shift_pv(audio, pitch_shift_semitones, sr=sr)
            # 2. Vocal Tract Length Normalization (VTLN) to scale vowel formants with pitch
            vtln_alpha = float(np.clip(2.0 ** ((pitch_shift_semitones / 12.0) * 0.35), 0.85, 1.20))
            if abs(vtln_alpha - 1.0) > 0.02:
                audio = AudioDSP.vtln_warp_spectrum(audio, vtln_alpha, sr=sr)

        # 3. Reshape frequency response to match user vocal tract spectral envelope
        if target_envelope is not None:
            source_env = AudioDSP.extract_spectral_envelope(audio, sr=sr)
            audio = AudioDSP.apply_spectral_envelope_transfer(
                source_audio=audio,
                target_env=target_envelope,
                source_env=source_env,
                sr=sr,
                strength=0.88,
            )
        elif target_embedding is not None and len(target_embedding) >= 80:
            # Fallback envelope from embedding mel energy distribution
            mel_profile = target_embedding[:80]
            eq_curve = (mel_profile - np.mean(mel_profile)) * 20.0  # Scale appropriately
            freq_bands = [100, 250, 500, 1000, 2000, 3000, 4500, 6000, 8000]
            for idx, center_freq in enumerate(freq_bands):
                if center_freq >= sr / 2:
                    break
                emb_idx = min(len(eq_curve) - 1, int((center_freq / 8000.0) * len(eq_curve)))
                gain_db = float(np.clip(eq_curve[emb_idx], -6.0, 6.0))
                if abs(gain_db) > 0.2:
                    q = 1.4
                    w0 = center_freq / (sr / 2)
                    bw = w0 / q
                    low = max(0.01, w0 - bw / 2)
                    high = min(0.99, w0 + bw / 2)
                    sos = scipy.signal.butter(2, [low, high], btype="bandpass", output="sos")
                    band_signal = scipy.signal.sosfilt(sos, audio)
                    linear_gain = 10.0 ** (gain_db / 20.0) - 1.0
                    audio += (band_signal * linear_gain).astype(np.float32)

        # 3. Peak normalize and write 16-bit PCM WAV
        final_audio = AudioDSP.normalize_peak(audio, target_db=-1.0)
        sf.write(str(output_wav_path), final_audio, sr, subtype="PCM_16")
        return output_wav_path
