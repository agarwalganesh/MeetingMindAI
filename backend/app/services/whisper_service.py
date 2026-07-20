import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from openai import OpenAI
from ..config import settings


def _register_cuda_dlls():
    """
    On Windows, ctranslate2 needs cuBLAS/cuDNN DLLs for GPU inference. If they
    were installed via pip (nvidia-cublas-cu12 / nvidia-cudnn-cu12), make their
    bin folders visible to the DLL loader. No-op when the packages are absent.
    """
    if os.name != "nt":
        return
    try:
        import nvidia
    except ImportError:
        return
    for pkg_dir in nvidia.__path__:
        for bin_dir in Path(pkg_dir).glob("*/bin"):
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                pass


_register_cuda_dlls()

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False

try:
    from transformers import AutoProcessor, VibeVoiceAsrForConditionalGeneration
    HAS_VIBEVOICE = True
except ImportError:
    HAS_VIBEVOICE = False

try:
    import librosa
    from transformers import pipeline as hf_pipeline
    HAS_SHUKA = True
except ImportError:
    HAS_SHUKA = False

# Optional acoustic speaker diarization. Heavy (pyannote.audio + torch) and the
# model is gated behind a HuggingFace token, so it is strictly optional — when
# absent, diarization degrades to a text-based heuristic.
try:
    from pyannote.audio import Pipeline as PyannotePipeline
    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False

# Preferred faster-whisper models, best quality first — all multilingual
# (Hindi, English, 90+ languages). The first one that loads successfully is
# kept for the lifetime of the process.
FASTER_WHISPER_MODELS = ["large-v3-turbo", "small", "tiny"]

VIBEVOICE_MODEL_ID = "microsoft/VibeVoice-ASR-HF"

# Sarvam AI's Indic speech-LLM (Bengali, English, Gujarati, Hindi, Kannada,
# Malayalam, Marathi, Oriya, Punjabi, Tamil, Telugu). 9B params — GPU server only.
SHUKA_MODEL_ID = "sarvamai/shuka-1"

MOCK_TRANSCRIPT = (
    "Alex: Good morning everyone, thanks for joining today's project kick-off meeting for our new client portal. "
    "I want to make sure we align on the scope and assign initial tasks. Sarah, can you give us an update on the UI/UX designs?\n"
    "Sarah: Hi Alex. Yes, the wireframes are about 80% complete. I am currently working on the user profile flow and the main dashboard. "
    "I should be able to finish all designs and upload them to Figma by Friday, June 19th.\n"
    "Alex: Perfect. Once the designs are in Figma, David, how long do you think it will take to build the frontend components?\n"
    "David: I will review the designs as soon as Sarah completes them. I can start building the React components on Monday. "
    "I plan to finish the core dashboard shell by next Wednesday, June 24th. I'll need the API documentation from backend first, though.\n"
    "Alex: Understood. Mike, you're handling the backend APIs, right? What is the status there?\n"
    "Mike: I've created the database schema. I will complete the API endpoint implementation and share the Swagger docs by Thursday, June 18th. "
    "That will give David plenty of time to integrate.\n"
    "Alex: Excellent. Let's make sure we document this. For key decisions, we agreed to use PostgreSQL for our main production database, and SQLite for local development. "
    "There is a small risk that database migrations might take longer than planned, so we need to monitor that closely.\n"
    "Sarah: Also, I think we should schedule a design review meeting next Tuesday at 10 AM to get client feedback before locking the final code.\n"
    "Alex: That's a great idea, Sarah. Let's schedule that. I will send out the calendar invite today. "
    "Overall, I'm feeling very optimistic about this project. The team is aligned, and the timeline is realistic. Let's keep up the momentum!"
)

class WhisperService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.client = None
        self.local_model = None
        self.local_device = None
        self.force_cpu = False
        self.vllm_client = None
        self.shuka_pipe = None
        self.vibevoice_model = None
        self.vibevoice_processor = None
        self.pyannote_pipeline = None
        if self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"):
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception as e:
                print(f"Error initializing OpenAI client: {e}")

    # ------------------- faster-whisper (primary local engine) -------------------

    def _model_candidates(self):
        preferred = (settings.WHISPER_MODEL or "").strip()
        candidates = [preferred] if preferred else []
        for name in FASTER_WHISPER_MODELS:
            if name not in candidates:
                candidates.append(name)
        return candidates

    def _device_candidates(self):
        """GPU first when CUDA is usable, always ending with a CPU fallback."""
        candidates = []
        if not self.force_cpu:
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() > 0:
                    candidates.append(("cuda", "int8_float16"))
            except Exception as e:
                print(f"CUDA detection failed ({e}). Using CPU...")
        candidates.append(("cpu", "int8"))
        return candidates

    def _initialize_local_model(self):
        if not HAS_FASTER_WHISPER:
            return None

        if self.local_model is None:
            print("Loading faster-whisper...")
            for model_name in self._model_candidates():
                for device, compute_type in self._device_candidates():
                    try:
                        print(
                            f"Downloading/loading model '{model_name}' on {device} "
                            f"(compute_type={compute_type})..."
                        )
                        self.local_model = WhisperModel(
                            model_name, device=device, compute_type=compute_type
                        )
                        self.local_device = device
                        print("Using GPU..." if device == "cuda" else "Using CPU...")
                        print(f"faster-whisper ready with model '{model_name}'.")
                        return self.local_model
                    except Exception as e:
                        print(f"Could not load '{model_name}' on {device}: {e}")
            self.local_model = None
        return self.local_model

    def _run_faster_whisper(self, model, file_path: str) -> str:
        segments, _ = model.transcribe(
            file_path,
            beam_size=5,
            vad_filter=True,  # skip silence: faster and more stable on long meetings
        )
        text = "\n".join(segment.text.strip() for segment in segments if segment.text.strip())
        print("Transcription completed.")
        return text

    def _run_faster_whisper_words(self, model, file_path: str) -> Tuple[List[Dict], str]:
        """Transcribe with word-level timestamps. Returns (words, plain_text)
        where each word is {"start", "end", "word"} — the timestamps let us
        align each word to a diarized speaker turn."""
        segments, _ = model.transcribe(
            file_path,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )
        words: List[Dict] = []
        texts: List[str] = []
        for segment in segments:
            seg_text = segment.text.strip()
            if seg_text:
                texts.append(seg_text)
            for w in (segment.words or []):
                words.append({"start": w.start, "end": w.end, "word": w.word})
        print("Transcription completed.")
        return words, "\n".join(texts)

    def _run_local(self, runner, file_path: str):
        """Run ``runner(model, file_path)`` against the local faster-whisper
        model, rebuilding once on CPU if GPU inference fails at runtime (e.g.
        missing cuDNN DLLs on Windows)."""
        model = self._initialize_local_model()
        if model is None:
            raise RuntimeError("No local faster-whisper model is available.")

        try:
            return runner(model, file_path)
        except Exception as e:
            if self.local_device == "cuda":
                print(f"GPU inference failed: {e}. Retrying on CPU...")
                self.force_cpu = True
                self.local_model = None
                model = self._initialize_local_model()
                if model is None:
                    raise
                return runner(model, file_path)
            raise

    def _transcribe_with_local_model(self, file_path: str) -> str:
        return self._run_local(self._run_faster_whisper, file_path)

    def _transcribe_and_diarize_local(self, file_path: str) -> str:
        """faster-whisper transcription with word timestamps, aligned to
        pyannote speaker turns. Falls back to a text heuristic when acoustic
        diarization is unavailable."""
        words, plain_text = self._run_local(self._run_faster_whisper_words, file_path)
        turns = self._diarize_with_pyannote(file_path)
        if turns:
            diarized = self._merge_words_and_turns(words, turns)
            if diarized.strip():
                return diarized
        return self._diarize_text_heuristic(plain_text)

    # ------------------- speaker diarization (optional pyannote + heuristic fallback) -------------------

    def _initialize_pyannote(self):
        """Lazily load the pyannote diarization pipeline. Returns None (and logs
        why) when the package is missing or no valid HuggingFace token is set."""
        if not HAS_PYANNOTE:
            return None

        token = (settings.HUGGINGFACE_TOKEN or "").strip()
        if not token or token.startswith("your_"):
            print(
                "Diarization: HUGGINGFACE_TOKEN not configured; "
                "skipping pyannote and using heuristic segmentation."
            )
            return None

        if self.pyannote_pipeline is None:
            try:
                print("Loading pyannote speaker diarization pipeline...")
                self.pyannote_pipeline = PyannotePipeline.from_pretrained(
                    settings.DIARIZATION_MODEL,
                    use_auth_token=token,
                )
                # Use the GPU when one is available for a large speedup.
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.pyannote_pipeline.to(torch.device("cuda"))
                        print("Diarization running on GPU.")
                except Exception:
                    pass
            except Exception as e:
                print(f"Failed to load pyannote diarization pipeline: {e}")
                self.pyannote_pipeline = None
        return self.pyannote_pipeline

    def _diarize_with_pyannote(self, file_path: str) -> Optional[List[Tuple[float, float, str]]]:
        """Return a list of (start, end, speaker_label) turns, or None if
        acoustic diarization is unavailable or fails."""
        pipeline = self._initialize_pyannote()
        if pipeline is None:
            return None
        try:
            diarization = pipeline(file_path)
            turns = [
                (turn.start, turn.end, speaker)
                for turn, _, speaker in diarization.itertracks(yield_label=True)
            ]
            return turns or None
        except Exception as e:
            print(f"pyannote diarization failed: {e}. Using heuristic segmentation.")
            return None

    def _merge_words_and_turns(
        self, words: List[Dict], turns: List[Tuple[float, float, str]]
    ) -> str:
        """Assign each transcribed word to the overlapping speaker turn, then
        group consecutive words by speaker into 'Speaker N: ...' lines."""
        if not words or not turns:
            return ""

        def speaker_for(w_start: float, w_end: float) -> str:
            best_speaker, best_overlap = None, 0.0
            for start, end, speaker in turns:
                overlap = min(w_end, end) - max(w_start, start)
                if overlap > best_overlap:
                    best_overlap, best_speaker = overlap, speaker
            if best_speaker is None:
                # No overlap (e.g. word in a gap) — pick the nearest turn.
                midpoint = (w_start + w_end) / 2
                best_speaker = min(
                    turns, key=lambda t: abs((t[0] + t[1]) / 2 - midpoint)
                )[2]
            return best_speaker

        # Map raw pyannote labels (SPEAKER_00, ...) to friendly, 1-based labels
        # in order of first appearance.
        label_map: Dict[str, str] = {}
        lines: List[str] = []
        current_speaker = None
        buffer: List[str] = []

        for w in words:
            w_start = w["start"] if w["start"] is not None else 0.0
            w_end = w["end"] if w["end"] is not None else w_start
            speaker = speaker_for(w_start, w_end)
            if speaker not in label_map:
                label_map[speaker] = f"Speaker {len(label_map) + 1}"

            if speaker != current_speaker and buffer:
                lines.append(f"{label_map[current_speaker]}: {''.join(buffer).strip()}")
                buffer = []
            current_speaker = speaker
            buffer.append(w["word"])

        if buffer and current_speaker is not None:
            lines.append(f"{label_map[current_speaker]}: {''.join(buffer).strip()}")

        return "\n".join(lines)

    def _diarize_text_heuristic(self, text: str) -> str:
        """Best-effort, dependency-free diarization from plain text.

        We cannot distinguish voices without the audio, so this only preserves
        explicit speaker cues that are already present ('Alex:', 'Speaker 2:',
        etc.) — which covers LLM speech-models and the mock transcript. When no
        such cues exist the text is returned unchanged (single speaker).
        """
        if not text or not text.strip():
            return text
        # Existing "Name:" / "Speaker N:" labels at the start of a line.
        if re.search(r'(?m)^\s*[A-Z][A-Za-z0-9 ._-]{0,30}:\s', text):
            return text.strip()
        return text.strip()

    # ------------------- remote vLLM speech-LLM (optional, e.g. Ultravox) -------------------

    def _transcribe_with_vllm(self, file_path: str) -> str:
        """
        Send audio to an OpenAI-compatible vLLM server running a speech-LLM
        (e.g. QuantumDesk-AI/ultravox-qwen3.6-27b-base served as 'ultravox').
        Only used when VLLM_BASE_URL is configured.
        """
        import base64

        if self.vllm_client is None:
            self.vllm_client = OpenAI(
                base_url=settings.VLLM_BASE_URL.strip(),
                api_key=settings.VLLM_API_KEY or "EMPTY",
            )

        mime_types = {
            "wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4",
            "mp4": "audio/mp4", "ogg": "audio/ogg", "flac": "audio/flac",
            "webm": "audio/webm", "aac": "audio/aac",
        }
        ext = os.path.splitext(file_path)[1].lstrip(".").lower()
        mime = mime_types.get(ext, "audio/wav")

        with open(file_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        response = self.vllm_client.chat.completions.create(
            model=settings.VLLM_MODEL,
            temperature=0.0,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "audio_url",
                        "audio_url": {"url": f"data:{mime};base64,{audio_b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Transcribe this meeting audio verbatim. "
                            "Output only the transcription text, nothing else."
                        ),
                    },
                ],
            }],
        )

        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise RuntimeError("vLLM server returned an empty transcription.")
        print("Transcription completed.")
        return text

    # ------------------- Shuka-1 Indic speech-LLM (optional, needs a 20GB+ VRAM GPU) -------------------

    def _initialize_shuka(self):
        if not HAS_SHUKA:
            return None

        if self.shuka_pipe is None:
            try:
                print("Loading Shuka-1 (Sarvam AI)...")
                self.shuka_pipe = hf_pipeline(
                    model=SHUKA_MODEL_ID,
                    trust_remote_code=True,
                    device_map="auto",
                    torch_dtype="bfloat16",
                )
            except Exception as e:
                print(f"Failed to initialize Shuka-1: {e}")
                self.shuka_pipe = None
        return self.shuka_pipe

    def _transcribe_with_shuka(self, file_path: str) -> str:
        pipe = self._initialize_shuka()
        if pipe is None:
            raise RuntimeError("Shuka-1 model is not available.")

        audio, sr = librosa.load(file_path, sr=16000)
        turns = [
            {
                "role": "system",
                "content": (
                    "Transcribe the audio verbatim in its original language "
                    "(e.g. Hindi in Devanagari, English in Latin script). "
                    "Output only the transcription text, nothing else."
                ),
            },
            {"role": "user", "content": "<|audio|>"},
        ]
        result = pipe(
            {"audio": audio, "turns": turns, "sampling_rate": sr},
            max_new_tokens=4096,
        )

        if isinstance(result, list) and result:
            result = result[0]
        if isinstance(result, dict):
            result = result.get("generated_text", "")

        text = str(result).strip()
        if not text:
            raise RuntimeError("Shuka-1 returned an empty transcription.")
        print("Transcription completed.")
        return text

    # ------------------- VibeVoice ASR (optional, needs a 16GB+ VRAM GPU) -------------------

    def _initialize_vibevoice(self):
        if not HAS_VIBEVOICE:
            return None

        if self.vibevoice_model is None:
            try:
                self.vibevoice_processor = AutoProcessor.from_pretrained(VIBEVOICE_MODEL_ID)
                self.vibevoice_model = VibeVoiceAsrForConditionalGeneration.from_pretrained(
                    VIBEVOICE_MODEL_ID,
                    dtype="auto",
                    device_map="auto",
                )
            except Exception as e:
                print(f"Failed to initialize VibeVoice ASR model: {e}")
                self.vibevoice_model = None
                self.vibevoice_processor = None
        return self.vibevoice_model

    def _transcribe_with_vibevoice(self, file_path: str) -> str:
        model = self._initialize_vibevoice()
        if model is None:
            raise RuntimeError("VibeVoice ASR model is not available.")

        inputs = self.vibevoice_processor.apply_transcription_request(
            audio=file_path
        ).to(model.device, model.dtype)

        output_ids = model.generate(**inputs)
        generated_ids = output_ids[:, inputs["input_ids"].shape[1]:]
        transcription = self.vibevoice_processor.decode(
            generated_ids, return_format="transcription_only"
        )[0]

        result = transcription.strip()
        if not result:
            raise RuntimeError("VibeVoice ASR returned an empty transcription.")
        return result

    # ------------------- public API -------------------

    def transcribe_audio(self, file_path: str, diarize: Optional[bool] = None) -> str:
        """
        Transcribe an audio file. Engines are tried in order:
        1. faster-whisper (local; GPU when CUDA is available, otherwise CPU;
           multilingual — Hindi, English, 90+ languages)
        2. Remote vLLM speech-LLM, e.g. Ultravox (when VLLM_BASE_URL is configured)
        3. OpenAI Whisper API (when an API key is configured)
        4. Shuka-1 Indic speech-LLM (optional, for future GPU server deployments)
        5. VibeVoice ASR (optional, for future GPU server deployments)
        6. Mock transcript (last resort so the API always returns a response)

        When ``diarize`` is true (defaults to settings.ENABLE_DIARIZATION), the
        transcript is segmented by speaker ("Speaker 1: ...", "Speaker 2: ...").
        The faster-whisper path uses acoustic diarization via pyannote when it is
        installed and a HuggingFace token is configured; every other path (and
        faster-whisper without pyannote) falls back to a text-based heuristic.
        """
        if diarize is None:
            diarize = settings.ENABLE_DIARIZATION

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found at {file_path}")

        # faster-whisper is the only local engine that exposes word timestamps,
        # so it is the one that can do true acoustic diarization.
        if HAS_FASTER_WHISPER:
            try:
                if diarize:
                    return self._transcribe_and_diarize_local(file_path)
                return self._transcribe_with_local_model(file_path)
            except Exception as e:
                print(f"faster-whisper transcription failed: {e}. Fallback to next engine...")
        else:
            print("faster-whisper is not installed. Fallback to next engine...")

        # Remaining engines return a plain string; apply the text-based
        # diarization heuristic afterwards if diarization was requested.
        text = self._transcribe_with_remote_engines(file_path)
        return self._diarize_text_heuristic(text) if diarize else text

    def _transcribe_with_remote_engines(self, file_path: str) -> str:
        """The non-faster-whisper engine chain, each producing a plain transcript."""
        if settings.VLLM_BASE_URL and settings.VLLM_BASE_URL.strip():
            try:
                return self._transcribe_with_vllm(file_path)
            except Exception as e:
                print(f"vLLM (Ultravox) transcription failed: {e}. Fallback to OpenAI...")

        if self.client:
            try:
                with open(file_path, "rb") as audio_file:
                    transcript_obj = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                    print("Transcription completed.")
                    return transcript_obj.text
            except Exception as e:
                print(f"OpenAI Whisper API failed: {e}. Fallback to next engine...")

        if HAS_SHUKA:
            try:
                return self._transcribe_with_shuka(file_path)
            except Exception as e:
                print(f"Shuka-1 transcription failed: {e}. Fallback to VibeVoice...")

        if HAS_VIBEVOICE:
            try:
                return self._transcribe_with_vibevoice(file_path)
            except Exception as e:
                print(f"VibeVoice ASR transcription failed: {e}.")

        print("Fallback to Mock Transcript...")
        return MOCK_TRANSCRIPT

whisper_service = WhisperService()
