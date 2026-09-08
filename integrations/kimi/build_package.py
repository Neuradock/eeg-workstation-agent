"""Build reproducible, allowlisted skill archives without recordings or secrets."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / "skills/neuradock-eeg"
FILES = ["SKILL.md", "LICENSE", "requirements.txt", "scripts/neuradock_toolkit.py",
         "references/applications.md", "references/scientific-boundaries.md",
         "references/data-format.md", "references/device-profile.md", "references/analysis.md"]


def main():
    dest = ROOT / "downloads"
    dest.mkdir(exist_ok=True)
    archive = dest / "neuradock-eeg-0.1.0-beta.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for name in FILES:
            item = ZipInfo("neuradock-eeg/" + name, date_time=(2026, 9, 8, 0, 0, 0))
            item.compress_type = ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            content = (SKILL / name).read_text(encoding="utf-8").replace("\r\n", "\n")
            output.writestr(item, content.encode("utf-8"), compresslevel=9)
    skill_archive = dest / "kimi_neuradock-eeg-0.1.0-beta.skill"
    skill_archive.write_bytes(archive.read_bytes())
    with ZipFile(archive) as check:
        assert check.testzip() is None
        assert len(check.namelist()) == len(FILES)
    sums = [f"{sha256(file.read_bytes()).hexdigest()}  {file.name}"
            for file in (archive, skill_archive)]
    (dest / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print("Packaged", len(FILES), "files")


if __name__ == "__main__":
    main()
