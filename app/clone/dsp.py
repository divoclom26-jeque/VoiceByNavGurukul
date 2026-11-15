import logging
import math
from pathlib import Path
from typing import Any, Dict, Tuple
import numpy as np
import scipy.signal
import soundfile as sf

logger = logging.getLogger(__name__)


class AudioDSP:
    """Digital Signal Processing utilities for Voice Cloning reference audio cleaning and feature extraction."""

    @staticmethod
    def highpass_filter(audio: np.ndarray, sr: int, cutoff: float = 65.0) -> np.ndarray:
        """Apply a 2nd-order Butterworth high-pass filter to remove low-frequency rumble and mic thumps."""
        if len(audio) == 0:
            return audio
        nyquist = 0.5 * sr
        norm_cutoff = min(0.99, max(0.01, cutoff / nyquist))
        sos = scipy.signal.butter(2, norm_cutoff, btype="highpass", output="sos")
        return scipy.signal.sosfilt(sos, audio).astype(np.float32)

    @staticmethod
    def spectral_denoise(
        audio: np.ndarray,
        sr: int,
        noise_reduction_amount: float = 0.75,
        noise_floor: float = 0.05,
    ) -> np.ndarray:
        """Perform stationary spectral noise subtraction to silence background fan/air noise."""
        if len(audio) < 1024:
            return audio

        n_fft = 1024
        hop_length = 256
        window = np.hanning(n_fft)

        # Compute STFT
        f, t, zxx = scipy.signal.stft(audio, fs=sr, window=window, nperseg=n_fft, noverlap=n_fft - hop_length)
        magnitude = np.abs(zxx)
        phase = np.angle(zxx)

        # Estimate noise profile from lowest 15% energy frames
        frame_energies = np.sum(magnitude**2, axis=0)
        n_noise_frames = max(2, int(len(frame_energies) * 0.15))
        lowest_energy_indices = np.argsort(frame_energies)[:n_noise_frames]
        noise_profile = np.mean(magnitude[:, lowest_energy_indices], axis=1, keepdims=True)

        # Spectral subtraction with soft flooring
        clean_mag = magnitude - (noise_reduction_amount * noise_profile)
        clean_mag = np.maximum(clean_mag, noise_floor * magnitude)

        # Reconstruct waveform via ISTFT
        clean_zxx = clean_mag * np.exp(1j * phase)
        _, clean_audio = scipy.signal.istft(clean_zxx, fs=sr, window=window, nperseg=n_fft, noverlap=n_fft - hop_length)

        # Match original length
        if len(clean_audio) > len(audio):
            clean_audio = clean_audio[:len(audio)]
        elif len(clean_audio) < len(audio):
            clean_audio = np.pad(clean_audio, (0, len(audio) - len(clean_audio)))

        return clean_audio.astype(np.float32)

    @staticmethod
    def vad_trim_silence(
        audio: np.ndarray,
        sr: int,
        threshold_db: float = 30.0,
        frame_ms: int = 30,
        pad_ms: int = 100,
    ) -> np.ndarray:
        """Trim leading and trailing silence using short-term energy envelope with margin padding."""
        if len(audio) == 0:
            return audio

        frame_len = max(16, int(sr * (frame_ms / 1000.0)))
        hop = frame_len // 2
        num_frames = (len(audio) - frame_len) // hop + 1
        if num_frames <= 0:
            return audio

        # Calculate RMS energy per frame
        frames = np.lib.stride_tricks.sliding_window_view(audio, frame_len)[::hop]
        rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
        rms_db = 20 * np.log10(rms / (np.max(rms) + 1e-12))

        active_indices = np.where(rms_db > -threshold_db)[0]
        if len(active_indices) == 0:
            return audio

        pad_samples = int(sr * (pad_ms / 1000.0))
        start_sample = max(0, active_indices[0] * hop - pad_samples)
        end_sample = min(len(audio), active_indices[-1] * hop + frame_len + pad_samples)

        return audio[start_sample:end_sample].astype(np.float32)

    @staticmethod
    def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Resample audio using polynomial polyphase filtering."""
        if orig_sr == target_sr or len(audio) == 0:
            return audio.astype(np.float32)
        gcd = math.gcd(orig_sr, target_sr)
        up = target_sr // gcd
        down = orig_sr // gcd
        return scipy.signal.resample_poly(audio, up, down).astype(np.float32)

    @staticmethod
    def normalize_peak(audio: np.ndarray, target_db: float = -1.0) -> np.ndarray:
        """Normalize peak amplitude to target dBFS (default -1.0 dBFS)."""
        if len(audio) == 0:
            return audio
        peak = np.max(np.abs(audio))
        if peak < 1e-6:
            return audio
        target_amplitude = 10.0 ** (target_db / 20.0)
        gain = target_amplitude / peak
        return (audio * gain).astype(np.float32)

    @classmethod
    def clean_voice_sample(
        cls,
        input_path: Path,
        output_path: Path,
        target_sr: int = 22050,
        min_duration_sec: float = 2.0,
    ) -> Dict[str, Any]:
        """Load, denoise, filter, VAD-trim, and normalize user reference audio into a pristine WAV."""
        input_path = Path(input_path).resolve()
        if not input_path.is_file():
            raise FileNotFoundError(f"Reference audio file not found: {input_path}")

        data, sr = sf.read(str(input_path), dtype="float32")

        # Convert stereo to mono if necessary
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        # 1. High-pass filter (rumble strip)
        filtered = cls.highpass_filter(data, sr, cutoff=65.0)

        # 2. Spectral stationary noise reduction
        denoised = cls.spectral_denoise(filtered, sr, noise_reduction_amount=0.70)

        # 3. VAD silence trimming
        trimmed = cls.vad_trim_silence(denoised, sr, threshold_db=28.0)

        # 4. Resample to standard studio rate (22.05 kHz)
        resampled = cls.resample_audio(trimmed, sr, target_sr)

        # 5. Peak normalize
        normalized = cls.normalize_peak(resampled, target_db=-1.0)

        duration = len(normalized) / float(target_sr)
        if duration < min_duration_sec:
            raise ValueError(
                f"Audio sample duration ({duration:.2f}s) is too short. Please provide at least {min_duration_sec}s of clear speech."
            )

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), normalized, target_sr, subtype="PCM_16")

        return {
            "output_path": str(output_path),
            "sample_rate": target_sr,
            "duration": round(duration, 3),
            "samples": len(normalized),
        }

    @staticmethod
    def extract_mel_spectrogram(
        audio: np.ndarray,
        sr: int = 16000,
        n_mels: int = 80,
        n_fft: int = 512,
        hop_length: int = 160,
        win_length: int = 400,
        f_min: float = 80.0,
        f_max: float = 7600.0,
    ) -> np.ndarray:
        """Extract log Mel-spectrogram features in pure NumPy/SciPy."""
        if len(audio) == 0:
            return np.zeros((n_mels, 1), dtype=np.float32)

        window = np.hanning(win_length)
        # Pad audio to center frames
        pad_size = (n_fft - hop_length) // 2
        padded_audio = np.pad(audio, (pad_size, pad_size), mode="reflect")

        # Compute STFT
        _, _, stft = scipy.signal.stft(
            padded_audio,
            fs=sr,
            window=window,
            nperseg=win_length,
            noverlap=win_length - hop_length,
            nfft=n_fft,
            boundary=None,
            padded=False,
        )
        mag_spec = np.abs(stft)

        # Generate Mel filterbank
        def hz_to_mel(hz):
            return 2595.0 * np.log10(1.0 + hz / 700.0)

        def mel_to_hz(mel):
            return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

        mel_min = hz_to_mel(f_min)
        mel_max = hz_to_mel(f_max)
        mel_pts = np.linspace(mel_min, mel_max, n_mels + 2)
        hz_pts = mel_to_hz(mel_pts)
        bin_pts = np.floor((n_fft + 1) * hz_pts / sr).astype(int)

        fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
        for i in range(1, n_mels + 1):
            left = bin_pts[i - 1]
            center = bin_pts[i]
            right = bin_pts[i + 1]

            for j in range(left, center):
                if center > left:
                    fb[i - 1, j] = (j - left) / (center - left)
            for j in range(center, right):
                if right > center:
                    fb[i - 1, j] = (right - j) / (right - center)

        # Apply filterbank and log compression
        mel_spec = np.dot(fb, mag_spec[: n_fft // 2 + 1, :])
        log_mel = np.log(np.maximum(mel_spec, 1e-5))
        return log_mel.astype(np.float32)
