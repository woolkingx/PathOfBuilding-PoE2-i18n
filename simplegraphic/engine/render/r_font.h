// SimpleGraphic Engine
// (c) David Gowor, 2014
//
// Render Font Header
//

// =======
// Classes
// =======

#include <filesystem>
#include <istream>
#include <string>
#include <string_view>
#include <vector>

struct stbtt_fontinfo;

// Font
class r_font_c {
public:
	r_font_c(class r_renderer_c* renderer, const char* fontName);
	~r_font_c();

	int		StringWidth(int height, std::u32string_view str);
	int		StringCursorIndex(int height, std::u32string_view str, int curX, int curY);
	void	Draw(scp_t pos, int align, int height, col4_t col, std::u32string_view str);
	void	FDraw(scp_t pos, int align, int height, col4_t col, const char* fmt, ...);
	void	VDraw(scp_t pos, int align, int height, col4_t col, const char* fmt, va_list va);

private:
	int		StringWidthInternal(struct f_fontHeight_s* fh, std::u32string_view str, int height, float scale);
	size_t	StringCursorInternal(struct f_fontHeight_s* fh, std::u32string_view str, int height, float scale, int curX);
	void	DrawTextLine(scp_t pos, int align, int height, col4_t col, std::u32string_view str);
	bool	LoadLegacyFont(std::string const& fileNameBase, std::istream& tgf);
	bool	LoadTtfFont(std::string const& fileNameBase, std::string const& tgfText);
	bool	LoadTtfFaceFromConfig(std::string const& tgfText);
	bool	LoadTtfFace(std::filesystem::path const& ttfPath, float scale);
	bool	LoadFallbackFont();
	struct f_glyph_s const* GetGlyph(struct f_fontHeight_s* fh, char32_t cp);
	struct f_glyph_s const* RasterizeGlyph(struct f_fontHeight_s* fh, char32_t cp);
	void	BuildFontHeightMap();

	struct EmbeddedFontSpec {
		f_fontHeight_s* fh;
		int yPad;
	};
	EmbeddedFontSpec FindSmallerFontHeight(int height, int heightIdx, int sizeReduction);
	
	struct FontHeightEntry {
		f_fontHeight_s* fh;
		int heightIdx;
	};
	FontHeightEntry FindFontHeight(int height);

	class r_renderer_c* renderer = nullptr;
	std::vector<byte> ttfData;
	stbtt_fontinfo* ttfInfo = nullptr;
	float	ttfScale = 1.0f;
	int		numFontHeight = 0;
	struct f_fontHeight_s *fontHeights[32] = {};
	int		maxHeight = 0;
	int*	fontHeightMap = nullptr;
};
