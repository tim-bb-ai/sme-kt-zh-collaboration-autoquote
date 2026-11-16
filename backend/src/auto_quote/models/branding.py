from pydantic import BaseModel, Field


DEFAULT_LOGO_HEIGHT_MM = 14


class BrandColors(BaseModel):
    ink: str


# Font files by weight (300 light, 400 regular, 500 medium, 700 bold), as paths relative to the branding folder. They must be TrueType
# (.ttf), because the PDF library cannot embed OpenType fonts with PostScript outlines (.otf).
class BrandFont(BaseModel):
    family: str
    files: dict[int, str]


# The branding file is shared with the frontend; only the fields the backend uses are read.
class Branding(BaseModel):
    name: str
    details: str
    colors: BrandColors
    logo_height_mm: float = Field(default=DEFAULT_LOGO_HEIGHT_MM, alias="logoHeightMm")
    font: BrandFont | None = None
