-- Path of Building
--
-- Module: Lang
-- Loads UI translation tables and provides English fallback lookups.
--
local t_insert = table.insert
local t_concat = table.concat
local s_format = string.format
local tonumber = tonumber
local tostring = tostring

local lang = {
	defaultLocale = "en_US",
	currentLocale = "en_US",
	domains = { },
	searchAliases = { },
	statLiteralCache = { },
	available = {
		{ label = "English", locale = "en_US" },
		{ label = "简体中文", locale = "zh_CN" },
		{ label = "繁體中文", locale = "zh_TW" },
	},
}

local function loadDomain(locale, domain)
	if locale == lang.defaultLocale then
		return { }
	end
	local path = s_format("Data/Lang/%s/%s", locale, domain)
	local err, data = PCall(LoadModule, path)
	if err or type(data) ~= "table" then
		return { }
	end
	return data
end

function lang:SetLocale(locale)
	locale = locale or self.defaultLocale
	for _, localeInfo in ipairs(self.available) do
		if localeInfo.locale == locale then
			self.currentLocale = locale
			self.domains = { }
			self.searchAliases = { }
			self.statLiteralCache = { }
			return
		end
	end
	self.currentLocale = self.defaultLocale
	self.domains = { }
	self.searchAliases = { }
	self.statLiteralCache = { }
end

function lang:GetLocale()
	return self.currentLocale
end

function lang:GetLocaleList()
	local list = { }
	for _, localeInfo in ipairs(self.available) do
		t_insert(list, {
			label = localeInfo.label,
			locale = localeInfo.locale,
		})
	end
	return list
end

function lang:Tr(domain, msgid)
	if self.currentLocale == self.defaultLocale then
		return msgid
	end
	self.domains[domain] = self.domains[domain] or loadDomain(self.currentLocale, domain)
	return self.domains[domain][msgid] or msgid
end

function lang:Pob(msgid)
	return self:Tr("pob", msgid)
end

function lang:Data(domain, msgid)
	return self:Tr(domain, msgid)
end

function lang:Item(msgid)
	return self:Data("items", msgid)
end

function lang:Skill(msgid)
	return self:Data("skills", msgid)
end

local function statLiteralCandidate(text, signed)
	local values = { }
	local index = 0
	local candidate = text:gsub("[+-]?%d+%.?%d*", function(token)
		index = index + 1
		values[index] = token
		if signed and token:match("^[+-]") then
			return "{" .. (index - 1) .. ":+d}"
		end
		return "{" .. (index - 1) .. "}"
	end)
	if index == 0 then
		return nil
	end
	return candidate, values
end

local function applyStatLiteralValues(template, values)
	return template:gsub("{(%d+)([^}]*)}", function(index, spec)
		local value = values[tonumber(index) + 1]
		if not value then
			return "{" .. index .. spec .. "}"
		end
		if spec == ":+d" then
			return s_format("%+d", tonumber(value) or 0)
		elseif spec == ":d" then
			return s_format("%d", tonumber(value) or 0)
		end
		return tostring(value)
	end)
end

local function replacePlain(text, needle, replacement)
	if type(text) ~= "string" or type(needle) ~= "string" or needle == "" or type(replacement) ~= "string" then
		return text
	end
	local startIndex, endIndex = text:find(needle, 1, true)
	if not startIndex then
		return text
	end
	return text:sub(1, startIndex - 1) .. replacement .. text:sub(endIndex + 1)
end

function lang:StatLiteral(msgid)
	if self.currentLocale == self.defaultLocale or type(msgid) ~= "string" or msgid == "" then
		return msgid
	end
	local cached = self.statLiteralCache[msgid]
	if cached ~= nil then
		return cached
	end
	self.domains.stats = self.domains.stats or loadDomain(self.currentLocale, "stats")
	for _, signed in ipairs({ true, false }) do
		local candidate, values = statLiteralCandidate(msgid, signed)
		if candidate then
			local translated = self.domains.stats[candidate]
			if translated and translated ~= "" and translated ~= candidate then
				self.statLiteralCache[msgid] = applyStatLiteralValues(translated, values)
				return self.statLiteralCache[msgid]
			end
		end
	end
	self.statLiteralCache[msgid] = msgid
	return msgid
end

function lang:Stat(msgid)
	local translated = self:Data("stats", msgid)
	if translated ~= msgid then
		return translated
	end
	return self:StatLiteral(msgid)
end

function lang:Passive(msgid)
	local translated = self:Data("passives", msgid)
	if translated ~= msgid then
		return translated
	end
	translated = self:Stat(msgid)
	if translated ~= msgid then
		return translated
	end
	return self:Pob(msgid)
end

function lang:SkillDisplay(text)
	if type(text) ~= "string" or text == "" then
		return text
	end
	local translated = self:Skill(text)
	if translated ~= text then
		return translated
	end
	local prefix, suffix = text:match("^([^:]+):%s*(.+)$")
	if prefix and suffix then
		return self:Pob(prefix) .. ": " .. self:Skill(suffix)
	end
	return text
end

function lang:ItemDisplay(item)
	if type(item) == "string" then
		return self:Item(item)
	end
	if type(item) ~= "table" then
		return item
	end
	local name = item.name
	if type(name) ~= "string" or name == "" then
		return name
	end
	local exact = self:Item(name)
	if exact ~= name then
		return exact
	end
	if item.title then
		local baseName = type(item.baseName) == "string" and item.baseName:gsub(" %(.+%)", "") or ""
		if baseName ~= "" then
			return self:Item(item.title) .. ", " .. self:Item(baseName)
		end
		return self:Item(item.title)
	end
	local baseName = item.baseName
	if type(baseName) == "string" and baseName ~= "" then
		local baseMsgid = baseName:gsub(" %(.+%)", "")
		local translatedBase = self:Item(baseMsgid)
		if item.namePrefix or item.nameSuffix then
			return (item.namePrefix or "") .. translatedBase .. (item.nameSuffix or "")
		end
		if translatedBase ~= baseMsgid then
			return replacePlain(name, baseMsgid, translatedBase)
		end
	end
	return name
end

function lang:GetSearchAliases(domain, msgid)
	if type(msgid) ~= "string" or msgid == "" then
		return { msgid }
	end
	self.searchAliases[domain] = self.searchAliases[domain] or { }
	if self.searchAliases[domain][msgid] then
		return self.searchAliases[domain][msgid]
	end
	local aliases = { msgid }
	if self.currentLocale ~= self.defaultLocale then
		self.domains[domain] = self.domains[domain] or loadDomain(self.currentLocale, domain)
		local translated = self.domains[domain][msgid]
		if type(translated) == "string" and translated ~= "" and translated ~= msgid then
			t_insert(aliases, translated)
		end
	end
	self.searchAliases[domain][msgid] = aliases
	return aliases
end

function lang:SearchText(domain, msgid)
	return t_concat(self:GetSearchAliases(domain, msgid), "\n")
end

function lang:ItemSearchText(item)
	if type(item) ~= "table" then
		return self:SearchText("items", item)
	end
	local aliases = { item.name or "" }
	local display = self:ItemDisplay(item)
	if type(display) == "string" and display ~= "" and display ~= item.name then
		t_insert(aliases, display)
	end
	if type(item.baseName) == "string" then
		local baseName = item.baseName:gsub(" %(.+%)", "")
		for _, alias in ipairs(self:GetSearchAliases("items", baseName)) do
			t_insert(aliases, alias)
		end
	end
	if type(item.title) == "string" then
		for _, alias in ipairs(self:GetSearchAliases("items", item.title)) do
			t_insert(aliases, alias)
		end
	end
	return t_concat(aliases, "\n")
end

local function splitLeadingEscapes(text)
	local prefix = ""
	local rest = text
	while true do
		local color = rest:match("^(%^x%x%x%x%x%x%x)")
		if color then
			prefix = prefix .. color
			rest = rest:sub(#color + 1)
		else
			local short = rest:match("^(%^[%w%p])")
			if not short then
				break
			end
			prefix = prefix .. short
			rest = rest:sub(#short + 1)
		end
	end
	return prefix, rest
end

function lang:Ui(text)
	if type(text) ~= "string" or text == "" then
		return text
	end
	local leadingSpace, rest = text:match("^(%s*)(.*)$")
	local prefix, msgid = splitLeadingEscapes(rest)
	local labelSpace
	labelSpace, msgid = msgid:match("^(%s*)(.*)$")
	if msgid == "" then
		return text
	end
	return leadingSpace .. prefix .. labelSpace .. self:Pob(msgid)
end

function lang:UiFormat(text, ...)
	local translated = self:Ui(text)
	local ok, formatted = pcall(s_format, translated, ...)
	if ok then
		return formatted
	end
	return s_format(text, ...)
end

function TranslateUI(text)
	return lang:Ui(text)
end

function FormatUI(text, ...)
	return lang:UiFormat(text, ...)
end

function TranslateData(domain, text)
	return lang:Data(domain, text)
end

function TranslateItem(text)
	return lang:Item(text)
end

function TranslateItemDisplayName(item)
	return lang:ItemDisplay(item)
end

function TranslateItemDisplay(item)
	return lang:ItemDisplay(item)
end

function TranslateSkill(text)
	return lang:Skill(text)
end

function TranslateSkillDisplay(text)
	return lang:SkillDisplay(text)
end

function TranslateStat(text)
	return lang:Stat(text)
end

function TranslatePassive(text)
	return lang:Passive(text)
end

function GetLocalizedSearchAliases(domain, text)
	return lang:GetSearchAliases(domain, text)
end

function GetLocalizedSearchText(domain, text)
	return lang:SearchText(domain, text)
end

function GetLocalizedItemSearchText(item)
	return lang:ItemSearchText(item)
end

return lang
