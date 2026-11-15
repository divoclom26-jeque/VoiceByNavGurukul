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

    @classmethod
    def estimate_median_f0(cls, audio: np.ndarray, sr: int) -> float:
        """Estimate median fundamental pitch (F0 in Hz) using autocorrelation across voiced speech frames."""
        if len(audio) == 0:
            return 140.0
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        # Resample to 16kHz for uniform, robust pitch tracking
        if sr != 16000:
            new_len = int(len(audio) * 16000 / sr)
            audio = cls.resample_audio(audio, sr, 16000)
            sr = 16000

        frame_len = int(sr * 0.04)  # 40ms frame
        hop_len = int(sr * 0.02)    # 20ms hop
        min_lag = int(sr / 380)     # up to 380 Hz (female/child high pitch)
        max_lag = int(sr / 75)      # down to 75 Hz (deep bass male pitch)

        pitches = []
        for start in range(0, len(audio) - frame_len, hop_len):
            frame = audio[start : start + frame_len]
            rms = np.sqrt(np.mean(frame**2))
            if rms < 0.015:  # Skip unvoiced/silent frames
                continue

            corr = scipy.signal.correlate(frame, frame, mode="full")
            corr = corr[len(corr) // 2 :]
            if len(corr) < max_lag:
                continue

            lag_slice = corr[min_lag:max_lag]
            best_lag = min_lag + int(np.argmax(lag_slice))
            # Voicing confidence check (peak should be prominent compared to zero-lag)
            if corr[best_lag] > 0.32 * corr[0]:
                f0 = sr / float(best_lag)
                if 75.0 <= f0 <= 380.0:
                    pitches.append(f0)

        if not pitches:
            return 140.0
        return float(np.median(pitches))

    @staticmethod
    def time_stretch_phase_vocoder(
        audio: np.ndarray,
        rate: float,
        n_fft: int = 1024,
        hop: int = 256,
    ) -> np.ndarray:
        """Time-stretch audio using a fast Phase Vocoder in pure NumPy/SciPy without changing pitch."""
        if abs(rate - 1.0) < 0.01 or len(audio) < n_fft:
            return audio

        window = np.hanning(n_fft)
        f, t, Zxx = scipy.signal.stft(audio, nperseg=n_fft, noverlap=n_fft - hop, window=window)
        mag = np.abs(Zxx)
        phase = np.angle(Zxx)

        new_time_steps = np.arange(0, Zxx.shape[1] - 1, rate)
        if len(new_time_steps) == 0:
            return audio

        phase_adv = np.linspace(0, np.pi * hop, n_fft // 2 + 1)
        new_phase = np.zeros((Zxx.shape[0], len(new_time_steps)), dtype=np.float64)
        new_mag = np.zeros_like(new_phase)

        current_phase = phase[:, 0].astype(np.float64)
        for i, t_idx in enumerate(new_time_steps):
            left = int(np.floor(t_idx))
            right = min(left + 1, Zxx.shape[1] - 1)
            w = t_idx - left
            new_mag[:, i] = (1.0 - w) * mag[:, left] + w * mag[:, right]

            dphase = phase[:, right] - phase[:, left] - phase_adv
            dphase = dphase - 2.0 * np.pi * np.round(dphase / (2.0 * np.pi))
            current_phase += phase_adv + dphase
            new_phase[:, i] = current_phase

        Z_new = (new_mag * np.exp(1j * new_phase)).astype(np.complex64)
        _, x_stretched = scipy.signal.istft(Z_new, nperseg=n_fft, noverlap=n_fft - hop, window=window)
        return x_stretched.astype(np.float32)

    @classmethod
    def pitch_shift_pv(cls, audio: np.ndarray, semitones: float, sr: int = 22050) -> np.ndarray:
        """Shift pitch in semitones using SOLA period-synchronous overlap-add to prevent metallic phase artifacts."""
        if abs(semitones) < 0.15 or len(audio) < 1024:
            return audio
        return cls.pitch_shift_sola(audio, semitones, sr)

    @classmethod
    def pitch_shift_sola(cls, audio: np.ndarray, semitones: float, sr: int = 22050) -> np.ndarray:
        """High-Fidelity Synchronous Overlap-Add (SOLA) pitch shifting without phase smearing or metallic artifacts."""
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        if abs(semitones) < 0.15 or len(audio) < 1024:
            return audio

        factor = 2.0 ** (semitones / 12.0)
        target_len = max(64, int(len(audio) / factor))
        resampled = scipy.signal.resample(audio, target_len).astype(np.float32)

        win_len = int(sr * 0.035)   # 35ms window
        hop_out = int(sr * 0.015)   # 15ms output hop
        hop_in = max(1, int(hop_out * factor))

        if hop_in <= 0 or win_len <= 0 or len(resampled) < win_len:
            return audio

        num_hops = int(np.ceil((len(audio) - win_len) / hop_out)) + 1
        output = np.zeros(num_hops * hop_out + win_len, dtype=np.float32)
        norm = np.zeros_like(output)
        window = np.hanning(win_len).astype(np.float32)

        delta_max = int(sr * 0.006)  # 6ms search range for period alignment
        in_pos = 0
        out_pos = 0
        prev_grain = np.zeros(win_len, dtype=np.float32)

        for h in range(num_hops):
            best_pos = in_pos
            if h > 0 and in_pos + win_len + delta_max < len(resampled) and in_pos - delta_max >= 0:
                corr = np.correlate(
                    resampled[in_pos - delta_max : in_pos + win_len + delta_max],
                    prev_grain,
                    mode="valid",
                )
                best_pos = in_pos - delta_max + int(np.argmax(corr))

            grain_end = min(best_pos + win_len, len(resampled))
            grain = resampled[best_pos:grain_end]
            if len(grain) < win_len:
                grain = np.pad(grain, (0, win_len - len(grain)))

            output[out_pos : out_pos + win_len] += grain * window
            norm[out_pos : out_pos + win_len] += window
            prev_grain = grain

            in_pos += hop_in
            out_pos += hop_out
            if in_pos + win_len >= len(resampled):
                break

        norm = np.maximum(norm, 1e-4)
        result = output / norm
        if len(result) > len(audio):
            result = result[: len(audio)]
        elif len(result) < len(audio):
            result = np.pad(result, (0, len(audio) - len(result)))
        return result.astype(np.float32)

    @classmethod
    def vtln_warp_spectrum(cls, audio: np.ndarray, alpha: float, sr: int = 22050, n_fft: int = 1024, hop: int = 256) -> np.ndarray:
        """Vocal Tract Length Normalization (VTLN) frequency axis warping to adapt vowel formant positions."""
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        if abs(alpha - 1.0) < 0.02 or len(audio) < n_fft:
            return audio

        window = np.hanning(n_fft)
        _, _, Zxx = scipy.signal.stft(audio, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window=window)
        n_bins = Zxx.shape[0]
        freqs = np.linspace(0, sr / 2, n_bins)
        f_knee = sr / 4.0

        warped_freqs = np.zeros_like(freqs)
        for i, f in enumerate(freqs):
            if f <= f_knee:
                warped_freqs[i] = f * alpha
            else:
                warped_freqs[i] = alpha * f_knee + ((sr / 2.0 - alpha * f_knee) / (sr / 2.0 - f_knee)) * (f - f_knee)

        warped_indices = np.clip(warped_freqs / (sr / 2.0) * (n_bins - 1), 0, n_bins - 1)
        warped_Zxx = np.zeros_like(Zxx)

        for t in range(Zxx.shape[1]):
            mag = np.abs(Zxx[:, t])
            phase = np.angle(Zxx[:, t])
            warped_mag = np.interp(np.arange(n_bins), warped_indices, mag)
            warped_Zxx[:, t] = warped_mag * np.exp(1j * phase)

        _, warped_audio = scipy.signal.istft(warped_Zxx, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window=window)
        if len(warped_audio) > len(audio):
            warped_audio = warped_audio[: len(audio)]
        elif len(warped_audio) < len(audio):
            warped_audio = np.pad(warped_audio, (0, len(audio) - len(warped_audio)))
        return warped_audio.astype(np.float32)

    @staticmethod
    def extract_spectral_envelope(
        audio: np.ndarray,
        sr: int = 22050,
        n_fft: int = 1024,
        hop: int = 256,
        smoothing_sigma: float = 6.0,
    ) -> np.ndarray:
        """Extract a smooth vocal-tract spectral envelope from voiced frames."""
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        if len(audio) < n_fft:
            return np.ones(n_fft // 2 + 1, dtype=np.float32)

        window = np.hanning(n_fft)
        _, _, Zxx = scipy.signal.stft(audio, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window=window)
        mag = np.abs(Zxx)

        frame_energy = np.mean(mag, axis=0)
        thresh = np.percentile(frame_energy, 25)
        voiced_mag = mag[:, frame_energy > thresh]
        if voiced_mag.shape[1] == 0:
            voiced_mag = mag

        avg_spectrum = np.mean(voiced_mag, axis=1)
        log_spec = np.log1p(np.maximum(0, avg_spectrum))

        # Gaussian smoothing across frequency bins to isolate broad formant peaks
        from scipy.ndimage import gaussian_filter1d

        smooth_env = gaussian_filter1d(log_spec, sigma=smoothing_sigma)
        return smooth_env.astype(np.float32)

    @staticmethod
    def apply_spectral_envelope_transfer(
        source_audio: np.ndarray,
        target_env: np.ndarray,
        source_env: np.ndarray,
        sr: int = 22050,
        n_fft: int = 1024,
        hop: int = 256,
        strength: float = 0.85,
    ) -> np.ndarray:
        """Reshape source audio harmonics to match target speaker's vocal tract envelope."""
        if source_audio.ndim > 1:
            source_audio = np.mean(source_audio, axis=1)
        if len(source_audio) < n_fft or len(target_env) != len(source_env):
            return source_audio

        diff_log = target_env - source_env
        diff_log = diff_log - np.mean(diff_log)
        transfer_gain = np.exp(strength * diff_log)

        # Clamp gain between -12dB and +12dB to preserve natural dynamics
        transfer_gain = np.clip(transfer_gain, 0.25, 4.0).astype(np.float32)

        window = np.hanning(n_fft)
        _, _, Zxx = scipy.signal.stft(source_audio, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window=window)

        Zxx_morphed = (Zxx * transfer_gain[:, np.newaxis]).astype(np.complex64)
        _, morphed = scipy.signal.istft(Zxx_morphed, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, window=window)

        if len(morphed) > len(source_audio):
            morphed = morphed[: len(source_audio)]
        elif len(morphed) < len(source_audio):
            morphed = np.pad(morphed, (0, len(source_audio) - len(morphed)))

        return morphed.astype(np.float32)

