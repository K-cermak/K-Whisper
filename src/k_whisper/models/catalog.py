"""Known whisper.cpp GGML models hosted on Hugging Face."""

import re
from dataclasses import dataclass

WHISPER_REPO = "ggerganov/whisper.cpp"
VAD_REPO = "ggml-org/whisper-vad"
RECOMMENDED = "ggml-large-v3-turbo-q5_0.bin"


@dataclass(frozen=True)
class ModelInfo:
    filename: str
    size: int
    sha256: str = ""
    repo: str = WHISPER_REPO

    @property
    def name(self) -> str:
        return self.filename.removeprefix("ggml-").removesuffix(".bin")

    @property
    def url(self) -> str:
        return download_url(self.repo, self.filename)

    @property
    def description(self) -> str:
        return describe(self.filename)


VAD_MODEL = ModelInfo(
    "ggml-silero-v6.2.0.bin", 885_098, "2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987", VAD_REPO
)

# Offline fallback; sizes and checksums are refreshed from the Hugging Face API when online.
_BUILTIN = {
    "ggml-tiny.bin": (77_691_713, "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21"),
    "ggml-tiny-q5_1.bin": (32_152_673, "818710568da3ca15689e31a743197b520007872ff9576237bda97bd1b469c3d7"),
    "ggml-tiny-q8_0.bin": (43_537_433, "c2085835d3f50733e2ff6e4b41ae8a2b8d8110461e18821b09a15c40c42d1cca"),
    "ggml-tiny.en.bin": (77_704_715, "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"),
    "ggml-tiny.en-q5_1.bin": (32_166_155, "c77c5766f1cef09b6b7d47f21b546cbddd4157886b3b5d6d4f709e91e66c7c2b"),
    "ggml-tiny.en-q8_0.bin": (43_550_795, "5bc2b3860aa151a4c6e7bb095e1fcce7cf12c7b020ca08dcec0c6d018bb7dd94"),
    "ggml-base.bin": (147_951_465, "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"),
    "ggml-base-q5_1.bin": (59_707_625, "422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898"),
    "ggml-base-q8_0.bin": (81_768_585, "c577b9a86e7e048a0b7eada054f4dd79a56bbfa911fbdacf900ac5b567cbb7d9"),
    "ggml-base.en.bin": (147_964_211, "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"),
    "ggml-base.en-q5_1.bin": (59_721_011, "4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f"),
    "ggml-base.en-q8_0.bin": (81_781_811, "a4d4a0768075e13cfd7e19df3ae2dbc4a68d37d36a7dad45e8410c9a34f8c87e"),
    "ggml-small.bin": (487_601_967, "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"),
    "ggml-small-q5_1.bin": (190_085_487, "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb"),
    "ggml-small-q8_0.bin": (264_464_607, "49c8fb02b65e6049d5fa6c04f81f53b867b5ec9540406812c643f177317f779f"),
    "ggml-small.en.bin": (487_614_201, "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"),
    "ggml-small.en-q5_1.bin": (190_098_681, "bfdff4894dcb76bbf647d56263ea2a96645423f1669176f4844a1bf8e478ad30"),
    "ggml-small.en-q8_0.bin": (264_477_561, "67a179f608ea6114bd3fdb9060e762b588a3fb3bd00c4387971be4d177958067"),
    "ggml-medium.bin": (1_533_763_059, "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208"),
    "ggml-medium-q5_0.bin": (539_212_467, "19fea4b380c3a618ec4723c3eef2eb785ffba0d0538cf43f8f235e7b3b34220f"),
    "ggml-medium-q8_0.bin": (823_369_779, "42a1ffcbe4167d224232443396968db4d02d4e8e87e213d3ee2e03095dea6502"),
    "ggml-medium.en.bin": (1_533_774_781, "cc37e93478338ec7700281a7ac30a10128929eb8f427dda2e865faa8f6da4356"),
    "ggml-medium.en-q5_0.bin": (539_225_533, "76733e26ad8fe1c7a5bf7531a9d41917b2adc0f20f2e4f5531688a8c6cd88eb0"),
    "ggml-medium.en-q8_0.bin": (823_382_461, "43fa2cd084de5a04399a896a9a7a786064e221365c01700cea4666005218f11c"),
    "ggml-large-v1.bin": (3_094_623_691, "7d99f41a10525d0206bddadd86760181fa920438b6b33237e3118ff6c83bb53d"),
    "ggml-large-v2.bin": (3_094_623_691, "9a423fe4d40c82774b6af34115b8b935f34152246eb19e80e376071d3f999487"),
    "ggml-large-v2-q5_0.bin": (1_080_732_091, "3a214837221e4530dbc1fe8d734f302af393eb30bd0ed046042ebf4baf70f6f2"),
    "ggml-large-v2-q8_0.bin": (1_656_129_691, "fef54e6d898246a65c8285bfa83bd1807e27fadf54d5d4e81754c47634737e8c"),
    "ggml-large-v3.bin": (3_095_033_483, "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2"),
    "ggml-large-v3-q5_0.bin": (1_081_140_203, "d75795ecff3f83b5faa89d1900604ad8c780abd5739fae406de19f23ecd98ad1"),
    "ggml-large-v3-turbo.bin": (1_624_555_275, "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"),
    "ggml-large-v3-turbo-q5_0.bin": (574_041_195, "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"),
    "ggml-large-v3-turbo-q8_0.bin": (874_188_075, "317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1"),
}

BUILTIN_CATALOG = [ModelInfo(name, size, sha256) for name, (size, sha256) in _BUILTIN.items()]

_FAMILY_ORDER = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3", "large-v3-turbo"]
_NAME_RE = re.compile(r"^ggml-(?P<family>[a-z0-9-]+?)(?P<en>\.en)?(?:-(?P<quant>q\d_\d))?\.bin$")


def parse_name(filename: str) -> tuple[str, bool, str]:
    """Return (family, english_only, quantization) for a GGML model file name."""
    m = _NAME_RE.match(filename)
    if not m:
        return (filename.removesuffix(".bin"), False, "")
    return (m["family"], bool(m["en"]), m["quant"] or "")


def describe(filename: str) -> str:
    family, english, quant = parse_name(filename)
    title = family.replace("-", " ").replace("turbo", "Turbo")
    languages = "English only" if english else "all languages"
    size = f"compressed ({quant.split('_')[0].upper()})" if quant else "uncompressed"
    return f"{title[:1].upper()}{title[1:]}, {languages}, {size}"


def sort_key(info: ModelInfo) -> tuple:
    family, english, quant = parse_name(info.filename)
    order = _FAMILY_ORDER.index(family) if family in _FAMILY_ORDER else len(_FAMILY_ORDER)
    return (order, english, quant)


def download_url(repo: str, filename: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{filename}"


def tree_url(repo: str = WHISPER_REPO) -> str:
    return f"https://huggingface.co/api/models/{repo}/tree/main"


def parse_tree(entries: list[dict]) -> list[ModelInfo]:
    models = [
        ModelInfo(e["path"], int(e.get("size", 0)), (e.get("lfs") or {}).get("oid", ""))
        for e in entries
        if e.get("type", "file") == "file" and re.match(r"^ggml-.*\.bin$", e.get("path", ""))
    ]
    return sorted(models, key=sort_key)


def format_size(size: int) -> str:
    """Decimal units, as Hugging Face and macOS show them."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} GB"
