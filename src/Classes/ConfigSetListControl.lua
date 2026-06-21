-- Path of Building
--
-- Class: Config Set List
-- Config Set list control
--
local s_format = string.format

local function tr(text)
	return TranslateUI and TranslateUI(text) or text
end

local function formatUI(text, ...)
	return FormatUI and FormatUI(text, ...) or s_format(text, ...)
end

local ConfigSetListClass = newClass("ConfigSetListControl", "ListControl", function(self, anchor, rect, configTab)
	self.ListControl(anchor, rect, 16, "VERTICAL", true, configTab.configSetOrderList)
	self.configTab = configTab
	self.configSetService = new("ConfigSetService", configTab)
	self.controls.copy = new("ButtonControl", { "BOTTOMLEFT", self, "TOP" }, { 2, -4, 60, 18 }, tr("Copy"), function()
		self:CopyConfigSet(self.selValue)
	end)
	self.controls.copy.enabled = function()
		return self.selValue ~= nil
	end
	self.controls.delete = new("ButtonControl", { "LEFT", self.controls.copy, "RIGHT" }, { 4, 0, 60, 18 }, tr("Delete"),
		function()
			self:OnSelDelete(self.selIndex, self.selValue)
		end)
	self.controls.delete.enabled = function()
		return self.selValue ~= nil and #self.list > 1
	end
	self.controls.rename = new("ButtonControl", { "BOTTOMRIGHT", self, "TOP" }, { -2, -4, 60, 18 }, tr("Rename"), function()
		self:RenameConfigSet(self.selValue)
	end)
	self.controls.rename.enabled = function()
		return self.selValue ~= nil
	end
	self.controls.new = new("ButtonControl", { "RIGHT", self.controls.rename, "LEFT" }, { -4, 0, 60, 18 }, tr("New"),
		function()
			self:CreateConfigSet()
		end)
end)

function ConfigSetListClass:CreateConfigSet()
	local controls = {}
	controls.label = new("LabelControl", nil, { 0, 20, 0, 16 }, tr("^7Enter name for new config set:"))
	controls.edit = new("EditControl", nil, { 0, 40, 350, 20 }, "New Config Set", nil, nil, 100, function(buf)
		controls.save.enabled = buf:match("%S")
	end)
	controls.save = new("ButtonControl", nil, { -45, 70, 80, 20 }, tr("Save"), function()
		self.configSetService:NewConfigSet(controls.edit.buf)
		main:ClosePopup()
	end)
	controls.save.enabled = false
	controls.cancel = new("ButtonControl", nil, { 45, 70, 80, 20 }, tr("Cancel"), function()
		main:ClosePopup()
	end)
	main:OpenPopup(370, 100, tr("Create Config Set"), controls, "save", "edit", "cancel")
end

function ConfigSetListClass:CopyConfigSet(selValue)
	local configSet = self.configTab.configSets[selValue]
	local controls = {}
	controls.label = new("LabelControl", nil, { 0, 20, 0, 16 }, tr("^7Enter name for this config set:"))
	controls.edit = new("EditControl", nil, { 0, 40, 350, 20 }, configSet.title or "Default", nil, nil, 100, function(buf)
		controls.save.enabled = buf:match("%S")
	end)
	controls.save = new("ButtonControl", nil, { -45, 70, 80, 20 }, tr("Save"), function()
		self.configSetService:CopyConfigSet(selValue, controls.edit.buf)
		main:ClosePopup()
	end)
	controls.save.enabled = false
	controls.cancel = new("ButtonControl", nil, { 45, 70, 80, 20 }, tr("Cancel"), function()
		main:ClosePopup()
	end)
	main:OpenPopup(370, 100, tr("Copy Config Set"), controls, "save", "edit", "cancel")
end

function ConfigSetListClass:RenameConfigSet(selValue)
	local configSet = self.configTab.configSets[selValue]
	local controls = {}
	local specName = configSet.title or "Default"
	controls.label = new("LabelControl", nil, { 0, 20, 0, 16 }, tr("^7Enter name for this config set:"))
	controls.edit = new("EditControl", nil, { 0, 40, 350, 20 }, specName, nil, nil, 100, function(buf)
		controls.save.enabled = buf:match("%S")
	end)
	controls.save = new("ButtonControl", nil, { -45, 70, 80, 20 }, tr("Save"), function()
		self.configSetService:RenameConfigSet(selValue, controls.edit.buf)
		main:ClosePopup()
	end)
	controls.save.enabled = false
	controls.cancel = new("ButtonControl", nil, { 45, 70, 80, 20 }, tr("Cancel"), function()
		main:ClosePopup()
	end)
	main:OpenPopup(370, 100, specName and tr("Rename Config Set") or tr("Set Name"), controls, "save", "edit", "cancel")
end

function ConfigSetListClass:GetRowValue(column, index, configSetId)
	local configSet = self.configTab.configSets[configSetId]
	if column == 1 then
		local title = configSet.title or "Default"
		return configSetId == self.configTab.activeConfigSetId and formatUI("%s  ^9(Current)", title) or title
	end
end

function ConfigSetListClass:OnOrderChange()
	self.configTab.modFlag = true
end

function ConfigSetListClass:OnSelClick(index, configSetId, doubleClick)
	if doubleClick and configSetId ~= self.configTab.activeConfigSetId then
		self.configTab:SetActiveConfigSet(configSetId)
		self.configTab:AddUndoState()
	end
end

function ConfigSetListClass:OnSelDelete(index, configSetId)
	local configSet = self.configTab.configSets[configSetId]
	if #self.list > 1 then
		main:OpenConfirmPopup(tr("Delete Config Set"),
			formatUI("Are you sure you want to delete '%s'?", configSet.title or "Default"), tr("Delete"), function()
				self.configSetService:DeleteConfigSet(configSetId, index)

				self.selIndex = nil
				self.selValue = nil
			end)
	end
end

function ConfigSetListClass:OnSelKeyDown(index, configSetId, key)
	if key == "F2" then
		self:RenameConfigSet(configSetId)
	end
end
