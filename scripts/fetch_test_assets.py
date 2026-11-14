"""Download the tiny model and the JFK sample used by the smoke test into test-assets/."""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_whispercpp import WHISPER_CPP_TAG  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "test-assets"

ASSETS = {
    "ggml-tiny.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
    "jfk.wav": f"https://raw.githubusercontent.com/ggml-org/whisper.cpp/{WHISPER_CPP_TAG}/samples/jfk.wav",
}


def main() -> None:
    DEST.mkdir(exist_ok=True)
    for name, url in ASSETS.items():
        target = DEST / name
        if target.exists():
            print(f"{name}: already present")
            continue
        print(f"{name}: downloading {url}", flush=True)
        tmp = target.with_suffix(target.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(target)


if __name__ == "__main__":
    main()
