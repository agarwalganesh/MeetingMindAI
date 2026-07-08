import os
from pathlib import Path
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

    def _transcribe_with_local_model(self, file_path: str) -> str:
        model = self._initialize_local_model()
        if model is None:
            raise RuntimeError("No local faster-whisper model is available.")

        try:
            return self._run_faster_whisper(model, file_path)
        except Exception as e:
            # CUDA can also fail at inference time (e.g. missing cuDNN DLLs on
            # Windows). Rebuild once on CPU before giving up on faster-whisper.
            if self.local_device == "cuda":
                print(f"GPU inference failed: {e}. Retrying on CPU...")
                self.force_cpu = True
                self.local_model = None
                model = self._initialize_local_model()
                if model is None:
                    raise
                return self._run_faster_whisper(model, file_path)
            raise

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

    def transcribe_audio(self, file_path: str) -> str:
        """
        Transcribe an audio file. Engines are tried in order:
        1. faster-whisper (local; GPU when CUDA is available, otherwise CPU;
           multilingual — Hindi, English, 90+ languages)
        2. Remote vLLM speech-LLM, e.g. Ultravox (when VLLM_BASE_URL is configured)
        3. OpenAI Whisper API (when an API key is configured)
        4. Shuka-1 Indic speech-LLM (optional, for future GPU server deployments)
        5. VibeVoice ASR (optional, for future GPU server deployments)
        6. Mock transcript (last resort so the API always returns a response)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found at {file_path}")

        if HAS_FASTER_WHISPER:
            try:
                return self._transcribe_with_local_model(file_path)
            except Exception as e:
                print(f"faster-whisper transcription failed: {e}. Fallback to next engine...")
        else:
            print("faster-whisper is not installed. Fallback to next engine...")

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
