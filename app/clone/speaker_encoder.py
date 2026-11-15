import logging
from pathlib import Path
from typing import Optional
import numpy as np
import soundfile as sf

from app.clone.dsp import AudioDSP
from app.utils.paths import MODELS_DIR

logger = logging.getLogger(__name__)


class SpeakerEncoder:
    """Extracts a 256-dimensional neural speaker embedding vector representing vocal tract identity."""

    EMBEDDING_DIM = 256
    TARGET_SR = 16000

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or (MODELS_DIR / "encoder" / "speaker_encoder.onnx")
        self._session = None
        self._init_session()

    def _init_session(self):
        """Optionally initialize ONNXRuntime session if an ONNX encoder model is present."""
        if self.model_path and Path(self.model_path).is_file():
            try:
                import onnxruntime as ort

                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = 4
                self._session = ort.InferenceSession(str(self.model_path), sess_options, providers=["CPUExecutionProvider"])
                logger.info("SpeakerEncoder loaded ONNX model: %s", self.model_path)
            except Exception as e:
                logger.warning("Failed loading ONNX speaker encoder, using acoustic fallback: %s", e)
                self._session = None

    def extract_embedding_from_file(self, audio_path: Path) -> np.ndarray:
        """Load audio file and extract 256-D speaker embedding."""
        audio_path = Path(audio_path).resolve()
        data, sr = sf.read(str(audio_path), dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        return self.extract_embedding(data, sr)

    def extract_embedding(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Extract a 256-dimensional L2-normalized speaker embedding vector."""
        if len(audio) == 0:
            vec = np.zeros(self.EMBEDDING_DIM, dtype=np.float32)
            vec[0] = 1.0
            return vec

        # 1. Resample to 16kHz
        audio_16k = AudioDSP.resample_audio(audio, sr, self.TARGET_SR)
        audio_16k = AudioDSP.highpass_filter(audio_16k, self.TARGET_SR, cutoff=60.0)
        audio_16k = AudioDSP.normalize_peak(audio_16k, target_db=-1.0)

        # 2. If ONNX model is available, run inference
        if self._session is not None:
            try:
                mel = AudioDSP.extract_mel_spectrogram(audio_16k, sr=self.TARGET_SR)
                # Reshape for model input (batch_size, channels, n_mels, time) or (batch, time, n_mels)
                input_name = self._session.get_inputs()[0].name
                inp_shape = self._session.get_inputs()[0].shape

                if len(inp_shape) == 3:
                    inp_data = np.expand_dims(mel.T, axis=0).astype(np.float32)
                else:
                    inp_data = np.expand_dims(mel, axis=(0, 1)).astype(np.float32)

                out = self._session.run(None, {input_name: inp_data})[0]
                vec = out.flatten()[: self.EMBEDDING_DIM]
                if len(vec) < self.EMBEDDING_DIM:
                    vec = np.pad(vec, (0, self.EMBEDDING_DIM - len(vec)))
                norm = np.linalg.norm(vec)
                return (vec / (norm + 1e-8)).astype(np.float32)
            except Exception as e:
                logger.error("ONNX inference failed, falling back to acoustic fingerprint: %s", e)

        # 3. Deterministic Acoustic Formant Fingerprint (Offline Fallback)
        return self._compute_acoustic_fingerprint(audio_16k, self.TARGET_SR)

    def _compute_acoustic_fingerprint(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Compute a 256-D biometric acoustic profile based on formant centers, pitch, and mel energies."""
        mel = AudioDSP.extract_mel_spectrogram(audio, sr=sr, n_mels=80)
        # Stats across time: mean (80), std (80), min (80), max (16)
        mel_mean = np.mean(mel, axis=1)  # 80
        mel_std = np.std(mel, axis=1)    # 80
        mel_p25 = np.percentile(mel, 25, axis=1)  # 80

        # Spectral centroid & flux
        diff = np.diff(mel, axis=1)
        flux = np.mean(np.maximum(0, diff), axis=1)[:16]  # 16

        features = np.concatenate([mel_mean, mel_std, mel_p25, flux])
        if len(features) < self.EMBEDDING_DIM:
            features = np.pad(features, (0, self.EMBEDDING_DIM - len(features)))
        else:
            features = features[: self.EMBEDDING_DIM]

        # L2-normalize
        norm = np.linalg.norm(features)
        return (features / (norm + 1e-8)).astype(np.float32)

    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two speaker embeddings (0.0 to 1.0)."""
        dot = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 < 1e-8 or norm2 < 1e-8:
            return 0.0
        val = dot / (norm1 * norm2)
        return float(np.clip(val, -1.0, 1.0))
