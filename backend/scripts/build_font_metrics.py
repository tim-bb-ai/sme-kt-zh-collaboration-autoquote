"""Write the advance widths and kerning pairs of a TrueType font to a JSON file for the quote template renderer.

Word sets text with kerning, so a PDF that must match a Word document needs the font's kerning pairs. ReportLab only reads
the widths, and fontTools is not a dependency of the app, so the pairs are extracted once, here:

    uv run --with fonttools python scripts/build_font_metrics.py data/quote_template/fonts/calibri.ttf

The JSON is written next to the font (calibri.metrics.json) and is referenced by the template as fonts.metrics.
"""

import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont


PAIR_POSITIONING = 2
EXTENSION = 9
# Latin-1 plus the punctuation used in Swiss German business letters.
CHARACTERS = [chr(code) for code in range(0x20, 0x7F)] + [chr(code) for code in range(0xA0, 0x100)] + list("«»‹›–—‘’‚“”„…•€™")


def read_kerning(font: TTFont) -> dict[tuple[str, str], int]:
    gpos = font["GPOS"].table
    lookup_indices = sorted(
        {index for record in gpos.FeatureList.FeatureRecord if record.FeatureTag == "kern" for index in record.Feature.LookupListIndex}
    )
    pairs: dict[tuple[str, str], int] = {}
    for lookup_index in lookup_indices:
        lookup = gpos.LookupList.Lookup[lookup_index]
        for subtable in lookup.SubTable:
            lookup_type = lookup.LookupType
            if lookup_type == EXTENSION:
                lookup_type, subtable = subtable.ExtensionLookupType, subtable.ExtSubTable
            if lookup_type != PAIR_POSITIONING:
                continue
            # The first subtable that covers a pair wins, as in the OpenType lookup order.
            if subtable.Format == 1:
                for first_index, first in enumerate(subtable.Coverage.glyphs):
                    for record in subtable.PairSet[first_index].PairValueRecord:
                        pairs.setdefault((first, record.SecondGlyph), getattr(record.Value1, "XAdvance", 0) or 0)
            elif subtable.Format == 2:
                second_glyphs_by_class: dict[int, list[str]] = {}
                for glyph, glyph_class in subtable.ClassDef2.classDefs.items():
                    second_glyphs_by_class.setdefault(glyph_class, []).append(glyph)
                for first in subtable.Coverage.glyphs:
                    class_record = subtable.Class1Record[subtable.ClassDef1.classDefs.get(first, 0)]
                    for second_class, record in enumerate(class_record.Class2Record):
                        value = getattr(record.Value1, "XAdvance", 0) if record.Value1 else 0
                        for second in second_glyphs_by_class.get(second_class, []):
                            pairs.setdefault((first, second), value or 0)
    return pairs


def main(font_path: Path) -> None:
    font = TTFont(font_path)
    cmap = font.getBestCmap()
    advances = {character: font["hmtx"][cmap[ord(character)]][0] for character in CHARACTERS if ord(character) in cmap}
    pairs = read_kerning(font)
    kerning = {
        first + second: pairs[(cmap[ord(first)], cmap[ord(second)])]
        for first in advances
        for second in advances
        if pairs.get((cmap[ord(first)], cmap[ord(second)]))
    }
    metrics = {"units_per_em": font["head"].unitsPerEm, "advances": advances, "kerning": kerning}
    output_path = font_path.with_suffix(".metrics.json")
    output_path.write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")
    print(f"{output_path}: {len(advances)} characters, {len(kerning)} kerning pairs")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
