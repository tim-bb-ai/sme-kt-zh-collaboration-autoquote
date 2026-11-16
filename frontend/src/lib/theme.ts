// Each key is the name of a CSS variable from styles.css, so the branding file stays the only place the brand colours are defined.
export const applyBrandColors = (brandColors: Record<string, string>): void => {
    Object.entries(brandColors).forEach(([variableName, color]) => document.documentElement.style.setProperty(`--${variableName}`, color));
};

// Registers the brand font's files and makes it the app font through --brand-font; without files the default fonts from styles.css stay.
export const applyBrandFont = (family: string | undefined, urlsByWeight: Record<string, string>): void => {
    if (family === undefined || Object.keys(urlsByWeight).length === 0) {
        return;
    }
    Object.entries(urlsByWeight).forEach(([weight, url]) => document.fonts.add(new FontFace(family, `url(${url})`, { weight })));
    document.documentElement.style.setProperty("--brand-font", `"${family}"`);
};
