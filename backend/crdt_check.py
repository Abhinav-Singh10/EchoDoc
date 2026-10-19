from pathlib import Path

from pycrdt import Doc, Text

folder = Path(__file__).resolve().parent.parent / "scratch" / "crdt"

doc = Doc()
text = doc.get("content", type=Text)

doc.apply_update((folder / "javascript.bin").read_bytes())
print("Python received:", str(text))

text += " from Python"
print("Python edited:", str(text))

(folder / "python.bin").write_bytes(doc.get_update())