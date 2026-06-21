// SimpleGraphic Engine
// (c) David Gowor, 2014
//
// Module: Render Font
//

#include "r_local.h"

#include <fmt/format.h>
#include <algorithm>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <iterator>
#include <regex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
#include <cmath>
#include <cctype>

#define STB_TRUETYPE_IMPLEMENTATION
#include "imstb_truetype.h"

// =======
// Classes
// =======

// Glyph parameters
struct f_glyph_s {
	float	tcLeft = 0.0;
	float	tcRight = 0.0;
	float	tcTop = 0.0;
	float	tcBottom = 0.0;
	int		width = 0;
	int		height = 0;
	int		yOffset = 0;
	int		spLeft = 0;
	int		spRight = 0;
	r_tex_c* tex = nullptr;
};

// Font height info
struct f_fontHeight_s {
	r_tex_c* tex = nullptr;
	int		height = 0;
	int		numGlyph = 0;
	bool	ttfBacked = false;
	f_glyph_s glyphs[128] = {};
	std::unordered_map<char32_t, f_glyph_s> unicodeGlyphs;
	f_glyph_s defGlyph{0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0};

	f_glyph_s const* LegacyGlyph(char ch) const {
		if ((unsigned char)ch >= numGlyph) {
			return nullptr;
		}
		return &glyphs[(unsigned char)ch];
	}
};

// ===========
// Font Loader
// ===========

r_font_c::r_font_c(r_renderer_c* renderer, const char* fontName)
	: renderer(renderer)
{
	numFontHeight = 0;
	fontHeightMap = NULL;

	std::string fileNameBase = fmt::format(CFG_DATAPATH "Fonts/{}", fontName);

	// Open info file
	std::string tgfName = fileNameBase + ".tgf";
	std::ifstream tgf(tgfName);
	if (!tgf) {
		renderer->sys->con->Warning("font \"%s\" not found", fontName);
		return;
	}

	maxHeight = 0;
	std::string tgfText((std::istreambuf_iterator<char>(tgf)), std::istreambuf_iterator<char>());
	auto first = std::find_if_not(tgfText.begin(), tgfText.end(), [](unsigned char ch) {
		return std::isspace(ch);
	});
	if (first != tgfText.end() && *first == '{') {
		if (!LoadTtfFont(fileNameBase, tgfText)) {
			renderer->sys->con->Warning("font \"%s\" TTF config failed", fontName);
		}
		return;
	}

	std::istringstream legacyInfo(tgfText);
	if (!LoadLegacyFont(fileNameBase, legacyInfo)) {
		renderer->sys->con->Warning("font \"%s\" legacy config failed", fontName);
	}
	LoadFallbackFont();
}

bool r_font_c::LoadLegacyFont(std::string const& fileNameBase, std::istream& tgf)
{
	f_fontHeight_s* fh = NULL;

	// Parse info file
	std::string sub;
	while (std::getline(tgf, sub)) {
		int h, x, y, w, sl, sr;
		if (sscanf(sub.c_str(), "HEIGHT %u;", &h) == 1) {
			// New height
			fh = new f_fontHeight_s;
			fontHeights[numFontHeight++] = fh;
			std::string tgaName = fmt::format("{}.{}.tga", fileNameBase, h);
			fh->tex = new r_tex_c(renderer->texMan, tgaName.c_str(), TF_NOMIPMAP);
			fh->height = h;
			if (h > maxHeight) {
				maxHeight = h;
			}
			fh->numGlyph = 0;
		}
		else if (fh && sscanf(sub.c_str(), "GLYPH %u %u %u %d %d;", &x, &y, &w, &sl, &sr) == 5) {
			// Add glyph
			if (fh->numGlyph >= 128) continue;
			f_glyph_s* glyph = &fh->glyphs[fh->numGlyph++];
			glyph->tcLeft = (float)x / fh->tex->fileWidth;
			glyph->tcRight = (float)(x + w) / fh->tex->fileWidth;
			glyph->tcTop = (float)y / fh->tex->fileHeight;
			glyph->tcBottom = (float)(y + fh->height) / fh->tex->fileHeight;
			glyph->width = w;
			glyph->height = fh->height;
			glyph->spLeft = sl;
			glyph->spRight = sr;
			glyph->tex = fh->tex;
		}
	}

	BuildFontHeightMap();
	return numFontHeight > 0;
}

void r_font_c::BuildFontHeightMap()
{
	if (numFontHeight <= 0) {
		return;
	}
	fontHeightMap = new int[maxHeight + 1];
	memset(fontHeightMap, 0, sizeof(int) * (maxHeight + 1));
	for (int i = 0; i < numFontHeight; i++) {
		int gh = fontHeights[i]->height;
		for (int h = gh; h <= maxHeight; h++) {
			fontHeightMap[h] = i;
		}
		if (i > 0) {
			int belowH = fontHeights[i - 1]->height;
			int lim = (gh - belowH - 1) / 2;
			for (int b = 0; b < lim; b++) {
				fontHeightMap[gh - b - 1] = i;
			}
		}
	}
}

bool r_font_c::LoadTtfFont(std::string const& fileNameBase, std::string const& tgfText)
{
	if (!LoadTtfFaceFromConfig(tgfText)) {
		return false;
	}

	static int const heights[] = { 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 48, 56, 64 };
	for (int h : heights) {
		auto fh = new f_fontHeight_s;
		fh->height = h;
		fh->ttfBacked = true;
		fontHeights[numFontHeight++] = fh;
		if (h > maxHeight) {
			maxHeight = h;
		}
	}

	BuildFontHeightMap();
	return true;
}

bool r_font_c::LoadTtfFaceFromConfig(std::string const& tgfText)
{
	std::smatch match;
	std::regex fileRe("\"file\"\\s*:\\s*\"([^\"]+)\"");
	if (!std::regex_search(tgfText, match, fileRe)) {
		return false;
	}

	std::string fontFile = match[1].str();
	std::regex scaleRe("\"scale\"\\s*:\\s*([0-9]+(?:\\.[0-9]+)?)");
	if (std::regex_search(tgfText, match, scaleRe)) {
		ttfScale = std::stof(match[1].str());
	}

	std::filesystem::path ttfPath = std::filesystem::u8path(fontFile);
	if (ttfPath.is_relative()) {
		ttfPath = std::filesystem::u8path(CFG_DATAPATH "Fonts") / ttfPath;
	}

	return LoadTtfFace(ttfPath, ttfScale);
}

bool r_font_c::LoadTtfFace(std::filesystem::path const& ttfPath, float scale)
{
	if (ttfInfo) {
		return true;
	}

	fileInputStream_c in;
	if (in.FileOpen(ttfPath, true)) {
		return false;
	}

	ttfData.resize(in.GetLen());
	if (ttfData.empty() || in.Read(ttfData.data(), ttfData.size())) {
		return false;
	}

	auto fontOffset = stbtt_GetFontOffsetForIndex(ttfData.data(), 0);
	if (fontOffset < 0) {
		return false;
	}

	ttfInfo = new stbtt_fontinfo;
	if (!stbtt_InitFont(ttfInfo, ttfData.data(), fontOffset)) {
		delete ttfInfo;
		ttfInfo = nullptr;
		return false;
	}

	ttfScale = scale;
	return true;
}

bool r_font_c::LoadFallbackFont()
{
	auto fallbackPath = std::filesystem::u8path(CFG_DATAPATH "Fonts/UnicodeFallback.tgf");
	std::ifstream fallback(fallbackPath);
	if (!fallback) {
		return false;
	}

	std::string fallbackText((std::istreambuf_iterator<char>(fallback)), std::istreambuf_iterator<char>());
	if (!LoadTtfFaceFromConfig(fallbackText)) {
		return false;
	}

	for (int i = 0; i < numFontHeight; ++i) {
		fontHeights[i]->ttfBacked = true;
	}
	return true;
}

f_glyph_s const* r_font_c::GetGlyph(f_fontHeight_s* fh, char32_t cp)
{
	if (cp <= 127 && fh->numGlyph > 0) {
		return fh->LegacyGlyph((char)(unsigned char)cp);
	}

	if (!fh->ttfBacked) {
		return nullptr;
	}

	auto found = fh->unicodeGlyphs.find(cp);
	if (found != fh->unicodeGlyphs.end()) {
		return &found->second;
	}
	return RasterizeGlyph(fh, cp);
}

f_glyph_s const* r_font_c::RasterizeGlyph(f_fontHeight_s* fh, char32_t cp)
{
	if (!ttfInfo || !fh->ttfBacked) {
		return nullptr;
	}

	int glyphIndex = stbtt_FindGlyphIndex(ttfInfo, (int)cp);
	if (glyphIndex == 0 && cp != 0) {
		return nullptr;
	}

	float scale = stbtt_ScaleForPixelHeight(ttfInfo, fh->height * ttfScale);
	int advanceWidth = 0;
	int leftSideBearing = 0;
	stbtt_GetCodepointHMetrics(ttfInfo, (int)cp, &advanceWidth, &leftSideBearing);

	int ascent = 0;
	int descent = 0;
	int lineGap = 0;
	stbtt_GetFontVMetrics(ttfInfo, &ascent, &descent, &lineGap);
	int baseline = (int)std::ceil(ascent * scale);

	int x0 = 0;
	int y0 = 0;
	int x1 = 0;
	int y1 = 0;
	stbtt_GetCodepointBitmapBox(ttfInfo, (int)cp, scale, scale, &x0, &y0, &x1, &y1);

	f_glyph_s glyph{};
	glyph.width = (std::max)(0, x1 - x0);
	glyph.height = (std::max)(0, y1 - y0);
	glyph.yOffset = baseline + y0;
	glyph.spLeft = x0;
	glyph.spRight = (int)std::ceil(advanceWidth * scale) - glyph.spLeft - glyph.width;

	if (glyph.width > 0 && glyph.height > 0) {
		std::vector<byte> bitmap((size_t)glyph.width * glyph.height);
		stbtt_MakeCodepointBitmap(ttfInfo, bitmap.data(), glyph.width, glyph.height, glyph.width, scale, scale, (int)cp);

		auto raw = std::make_unique<image_c>(renderer->sys->con);
		if (!raw->CopyRaw(IMGTYPE_GRAY, glyph.width, glyph.height, bitmap.data())) {
			return nullptr;
		}
		glyph.tex = new r_tex_c(renderer->texMan, std::move(raw), TF_NOMIPMAP | TF_CLAMP);
		glyph.tcRight = 1.0f;
		glyph.tcBottom = 1.0f;
	}

	auto inserted = fh->unicodeGlyphs.emplace(cp, glyph);
	return &inserted.first->second;
}

r_font_c::~r_font_c()
{
	// Delete textures
	for (int i = 0; i < numFontHeight; i++) {
		delete fontHeights[i]->tex;
		for (auto& entry : fontHeights[i]->unicodeGlyphs) {
			delete entry.second.tex;
		}
		delete fontHeights[i];
	}
	delete[] fontHeightMap;
	delete ttfInfo;
}

// =============
// Font Renderer
// =============

std::u32string BuildTofuString(char32_t cp) {
	// Format unhandled Unicode codepoints like U+0123, higher planes have wider numbers.
	fmt::memory_buffer buf;
	fmt::format_to(fmt::appender(buf), "[U+{:04X}]", (uint32_t)cp);
	std::u32string ret;
	ret.reserve(buf.size());
	std::copy(buf.begin(), buf.end(), std::back_inserter(ret));
	return ret;
}

int const tofuSizeReduction = 3;

static int GlyphAdvance(f_glyph_s const* glyph)
{
	if (!glyph) {
		return 0;
	}
	return glyph->width + glyph->spLeft + glyph->spRight;
}

int r_font_c::StringWidthInternal(f_fontHeight_s* fh, std::u32string_view str, int height, float scale)
{
	int heightIdx = (int)(std::find(fontHeights, fontHeights + numFontHeight, fh) - fontHeights);
	auto tofuFont = FindSmallerFontHeight(height, heightIdx, tofuSizeReduction);

	float width = 0.0f;
	for (size_t idx = 0; idx < str.size();) {
		auto ch = str[idx];
		int escLen = IsColorEscape(str.substr(idx));
		if (escLen) {
			idx += escLen;
		}
		else if (ch == U'\t') {
			int spWidth = GlyphAdvance(GetGlyph(fh, U' '));
			width += spWidth * 4 * scale;
			width = std::ceil(width);
			++idx;
		}
		else if (auto glyph = GetGlyph(fh, ch)) {
			width += GlyphAdvance(glyph) * scale;
			width = std::ceil(width);
			++idx;
		}
		else {
			auto tofu = BuildTofuString(ch);
			for (auto cp : tofu) {
				width += GlyphAdvance(GetGlyph(tofuFont.fh, cp));
				width = std::ceil(width);
			}
			++idx;
		}
	}
	return static_cast<int>(width);
}

int r_font_c::StringWidth(int height, std::u32string_view str)
{
	auto mainFont = FindFontHeight(height);
	f_fontHeight_s* fh = mainFont.fh;
	int max = 0;
	float const scale = (float)height / fh->height;
	for (auto I = str.begin(); I != str.end(); ++I) {
		auto lineEnd = std::find(I, str.end(), U'\n');
		if (I != lineEnd) {
			std::u32string_view line(&*I, std::distance(I, lineEnd));
			int lw = StringWidthInternal(fh, line, height, scale);
			max = (std::max)(max, lw);
		}
		if (lineEnd == str.end()) {
			break;
		}
		I = lineEnd;
	}
	return max;
}

size_t r_font_c::StringCursorInternal(f_fontHeight_s* fh, std::u32string_view str, int height, float scale, int curX)
{
	int heightIdx = (int)(std::find(fontHeights, fontHeights + numFontHeight, fh) - fontHeights);
	auto tofuFont = FindSmallerFontHeight(height, heightIdx, tofuSizeReduction);

	float x = 0.0f;
	auto I = str.begin();
	auto lineEnd = std::find(I, str.end(), U'\n');
	while (I != lineEnd) {
		auto tail = str.substr(std::distance(str.begin(), I));
		int escLen = IsColorEscape(tail);
		if (escLen) {
			I += escLen;
		}
		else if (*I == U'\t') {
			float fullWidth = GlyphAdvance(GetGlyph(fh, U' ')) * 4.0f * scale;
			float halfWidth = std::ceil(fullWidth / 2.0f);
			x += halfWidth;
			x = std::ceil(x);
			if (curX <= x) {
				break;
			}
			x += fullWidth - halfWidth;
			x = std::ceil(x);
			if (curX <= x) {
				break;
			}
			++I;
		}
		else if (auto glyph = GetGlyph(fh, *I)) {
			x += GlyphAdvance(glyph) * scale;
			x = std::ceil(x);
			if (curX <= x) {
				break;
			}
			++I;
		}
		else {
			auto tofu = BuildTofuString(*I);
			for (auto cp : tofu) {
				x += GlyphAdvance(GetGlyph(tofuFont.fh, cp));
				x = std::ceil(x);
				if (curX <= x) {
					return std::distance(str.begin(), I);
				}
			}
			++I;
		}
	}
	return std::distance(str.begin(), I);
}

int	r_font_c::StringCursorIndex(int height, std::u32string_view str, int curX, int curY)
{
	auto mainFont = FindFontHeight(height);
	f_fontHeight_s* fh = mainFont.fh;
	int lastIndex = 0;
	int lineY = height;
	float scale = (float)height / fh->height;

	auto I = str.begin();
	while (I != str.end()) {
		auto lineEnd = std::find(I, str.end(), U'\n');
		auto line = str.substr(std::distance(str.begin(), I), std::distance(I, lineEnd));
		lastIndex = (int)(StringCursorInternal(fh, line, height, scale, curX));
		if (curY <= lineY) {
			break;
		}
		if (lineEnd == str.end()) {
			break;
		}
		I = lineEnd + 1;
		lineY += height;
	}
	return (int)std::distance(str.begin(), I) + lastIndex;
}

r_font_c::EmbeddedFontSpec r_font_c::FindSmallerFontHeight(int height, int heightIdx, int sizeReduction) {
	EmbeddedFontSpec ret{};
	ret.fh = fontHeights[heightIdx];
	ret.yPad = 0;
	for (int tofuIdx = heightIdx - 1; tofuIdx >= 0; --tofuIdx) {
		auto candFh = fontHeights[tofuIdx];
		int heightDiff = height - candFh->height;
		if (heightDiff >= sizeReduction) {
			ret.fh = candFh;
			ret.yPad = (int)std::ceil(heightDiff / 2.0f);
			break;
		}
	}
	return ret;
}

r_font_c::FontHeightEntry r_font_c::FindFontHeight(int height) {
	FontHeightEntry ret{};
	if (height > maxHeight) {
		// Too large heights get the largest font size.
		ret.heightIdx = numFontHeight - 1;
	}
	else if (height < 0) {
		// Negative heights get the smallest font size.
		ret.heightIdx = 0;
	}
	else {
		ret.heightIdx = fontHeightMap[height];
	}
	ret.fh = fontHeights[ret.heightIdx];
	return ret;
}

void r_font_c::DrawTextLine(scp_t pos, int align, int height, col4_t col, std::u32string_view str)
{
	// Check if the line is visible
	if (pos[Y] >= renderer->sys->video->vid.size[1] || pos[Y] <= -height) {
		// Just process the colour codes
		while (!str.empty()) {
			// Check for escape character
			int escLen = IsColorEscape(str);
			if (escLen) {
				str = ReadColorEscape(str, col);
				col[3] = 1.0f;
				renderer->curLayer->Color(col);
				continue;
			}
			str = str.substr(1);
		}
		return;
	}

	// Find best height to use
	auto mainFont = FindFontHeight(height);
	f_fontHeight_s* fh = mainFont.fh;
	float scale = (float)height / fh->height;
	auto tofuFont = FindSmallerFontHeight(height, mainFont.heightIdx, tofuSizeReduction);

	// Calculate the string position
	float x = pos[X];
	float y = std::floor(pos[Y]);
	if (align != F_LEFT) {
		// Calculate the real width of the string
		float width = StringWidthInternal(fh, str, height, scale);
		switch (align) {
		case F_CENTRE:
			x = floor((renderer->VirtualScreenWidth() - width) / 2.0f + pos[X]);
			break;
		case F_RIGHT:
			x = floor(renderer->VirtualScreenWidth() - width - pos[X]);
			break;
		case F_CENTRE_X:
			x = floor(pos[X] - width / 2.0f);
			break;
		case F_RIGHT_X:
			x = floor(pos[X] - width);
			break;
		}
	}

	// Snap the starting x position to the pixel grid so the leading glyph isn't blurred.
	x = std::round(x);

	r_tex_c* curTex{};

	auto drawGlyph = [this, &curTex, &x, y](f_glyph_s const* glyph, float scale, int yShift) {
		if (!glyph) {
			return;
		}
		float cpY = y + (glyph->yOffset + yShift) * scale;
		r_tex_c* glyphTex = glyph->tex;
		if (glyphTex && curTex != glyphTex) {
			curTex = glyphTex;
			renderer->curLayer->Bind(glyphTex);
		}
		x += glyph->spLeft * scale;
		if (glyphTex && glyph->width && glyph->height) {
			float w = glyph->width * scale;
			float h = glyph->height * scale;
			if (x + w >= 0 && x < renderer->VirtualScreenWidth()) {
				renderer->curLayer->Quad(
					glyph->tcLeft, glyph->tcTop, x, cpY,
					glyph->tcRight, glyph->tcTop, x + w, cpY,
					glyph->tcRight, glyph->tcBottom, x + w, cpY + h,
					glyph->tcLeft, glyph->tcBottom, x, cpY + h
				);
			}
			x += w;
		}
		x += glyph->spRight * scale;
		x = std::ceil(x);
	};

	// Render the string
	for (auto tail = str; !tail.empty();) {
		auto ch = tail[0];
		// Check for escape character
		int escLen = IsColorEscape(tail);
		if (escLen) {
			tail = ReadColorEscape(tail, col);
			col[3] = 1.0f;
			renderer->curLayer->Color(col);
			continue;
		}

		// Handle tabs
		if (ch == U'\t') {
			int spWidth = GlyphAdvance(GetGlyph(fh, U' '));
			x+= (spWidth << 2) * scale;
			tail = tail.substr(1);
			continue;
		}

		// Draw glyph
		if (auto glyph = GetGlyph(fh, ch)) {
			drawGlyph(glyph, scale, 0);
		}
		else {
			auto tofu = BuildTofuString(ch);
			for (auto tofuCh : tofu) {
				drawGlyph(GetGlyph(tofuFont.fh, tofuCh), 1.0f, tofuFont.yPad);
			}
		}
		tail = tail.substr(1);
	}
}

void r_font_c::Draw(scp_t pos, int align, int height, col4_t col, std::u32string_view str)
{
	if (str.empty()) {
		pos[Y]+= height;
		return;
	}

	// Prepare for rendering
	renderer->curLayer->Color(col);

	// Separate into lines and render them
	for (auto I = str.begin(); I != str.end(); ++I) {
		auto lineEnd = std::find(I, str.end(), U'\n');
		if (I != lineEnd) {
			std::u32string_view line(&*I, std::distance(I, lineEnd));
			DrawTextLine(pos, align, height, col, line);
		}
		pos[Y] += height;
		if (lineEnd == str.end()) {
			break;
		}
		I = lineEnd;
	}
}

void r_font_c::FDraw(scp_t pos, int align, int height, col4_t col, const char* fmt, ...)
{
	va_list va;
	va_start(va, fmt);
	VDraw(pos, align, height, col, fmt, va);
	va_end(va);
}

void r_font_c::VDraw(scp_t pos, int align, int height, col4_t col, const char* fmt, va_list va)
{
	char str[65536];
	vsnprintf(str, 65535, fmt, va);
	str[65535] = 0;
	auto idxStr = IndexUTF8ToUTF32(str);
	Draw(pos, align, height, col, idxStr.text);
}
