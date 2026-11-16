import brandingFile from "../../branding/branding.json";
import logoUrl from "../../branding/logo.png";

// Font files by weight (300 light, 400 regular, 500 medium, 700 bold), as paths relative to the branding folder.
interface BrandFont {
    family: string;
    files: Record<string, string>;
}

// The optional fields may be missing from a branding file.
interface Branding {
    name: string;
    description: string;
    logoAlt: string;
    logoHeaderHeightPx?: number;
    font?: BrandFont;
    colors: Record<string, string>;
}

const branding: Branding = brandingFile;

const DEFAULT_LOGO_HEADER_HEIGHT_PX = 20;
// Licensed font files are git-ignored, so the glob only finds those present in this checkout.
const BRANDING_FONT_URLS = import.meta.glob<string>("../../branding/fonts/*", { eager: true, query: "?url", import: "default" });

export const APP_CONFIG = {
    name: branding.name,
    description: branding.description,
    logo: logoUrl,
    logoAlt: branding.logoAlt,
    logoHeaderHeightPx: branding.logoHeaderHeightPx ?? DEFAULT_LOGO_HEADER_HEIGHT_PX,
};

export const BRAND_COLORS = branding.colors;

export const BRAND_FONT_FAMILY = branding.font?.family;
// The brand font's file URLs by weight, only for the files that exist.
export const BRAND_FONT_URLS: Record<string, string> = Object.fromEntries(
    Object.entries(branding.font?.files ?? {}).flatMap(([weight, file]) => {
        const path = `../../branding/${file}`;
        return path in BRANDING_FONT_URLS ? [[weight, BRANDING_FONT_URLS[path]]] : [];
    }),
);
