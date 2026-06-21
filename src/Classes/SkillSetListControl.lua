-- Path of Building
--
-- Class: Skill Set List
-- Skill set list control.
--
local t_insert = table.insert
local t_remove = table.remove
local t_maxn = table.maxn
local m_max = math.max
local s_format = string.format

local function tr(text)
	return TranslateUI and TranslateUI(text) or text
end

local function formatUI(text, ...)
	return FormatUI and FormatUI(text, ...) or s_format(text, ...)
end

local SkillSetListClass = newClass("SkillSetListControl", "ListControl", function(self, anchor, rect, skillsTab)
	self.ListControl(anchor, rect, 16, "VERTICAL", true, skillsTab.skillSetOrderList)
	self.skillsTab = skillsTab
	self.skillsSetService = new("SkillsSetService", skillsTab)
	self.controls.copy = new("ButtonControl", { "BOTTOMLEFT", self, "TOP" }, { 2, -4, 60, 18 }, tr("Copy"), function()
		self:CopySkillSet(self.selValue)
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
		self:RenameSkillSet(self.selValue)
	end)
	self.controls.rename.enabled = function()
		return self.selValue ~= nil
	end
	self.controls.new = new("ButtonControl", { "RIGHT", self.controls.rename, "LEFT" }, { -4, 0, 60, 18 }, tr("New"),
		function()
			self:CreateSkillSet()
		end)
end)

function SkillSetListClass:CreateSkillSet()
	local controls = {}
	controls.label = new("LabelControl", nil, { 0, 20, 0, 16 }, tr("^7Enter name for new skill set:"))
	controls.edit = new("EditControl", nil, { 0, 40, 350, 20 }, "New Skill Set", nil, nil, 100, function(buf)
		controls.save.enabled = buf:match("%S")
	end)
	controls.save = new("ButtonControl", nil, { -45, 70, 80, 20 }, tr("Save"), function()
		self.skillsSetService:NewSkillSet(controls.edit.buf)
		main:ClosePopup()
	end)
	controls.save.enabled = false
	controls.cancel = new("ButtonControl", nil, { 45, 70, 80, 20 }, tr("Cancel"), function()
		main:ClosePopup()
	end)
	main:OpenPopup(370, 100, tr("Create Skill Set"), controls, "save", "edit", "cancel")
end

function SkillSetListClass:CopySkillSet(selValue)
	local skillSet = self.skillsTab.skillSets[selValue]
	local controls = {}
	local skillSetName = skillSet.title or "Default"
	controls.label = new("LabelControl", nil, { 0, 20, 0, 16 }, tr("^7Enter name for this skill set:"))
	controls.edit = new("EditControl", nil, { 0, 40, 350, 20 }, skillSetName, nil, nil, 100, function(buf)
		controls.save.enabled = buf:match("%S")
	end)
	controls.save = new("ButtonControl", nil, { -45, 70, 80, 20 }, tr("Save"), function()
		self.skillsSetService:CopySkillSet(selValue, controls.edit.buf)
		main:ClosePopup()
	end)
	controls.save.enabled = false
	controls.cancel = new("ButtonControl", nil, { 45, 70, 80, 20 }, tr("Cancel"), function()
		main:ClosePopup()
	end)
	main:OpenPopup(370, 100, tr("Copy Skill Set"), controls, "save", "edit", "cancel")
end

function SkillSetListClass:RenameSkillSet(selValue)
	local skillSet = self.skillsTab.skillSets[selValue]
	local controls = {}
	local skillSetName = skillSet.title or "Default"
	controls.label = new("LabelControl", nil, { 0, 20, 0, 16 }, tr("^7Enter name for this skill set:"))
	controls.edit = new("EditControl", nil, { 0, 40, 350, 20 }, skillSetName, nil, nil, 100, function(buf)
		controls.save.enabled = buf:match("%S")
	end)
	controls.save = new("ButtonControl", nil, { -45, 70, 80, 20 }, tr("Save"), function()
		self.skillsSetService:RenameSkillSet(selValue, controls.edit.buf)
		main:ClosePopup()
	end)
	controls.save.enabled = false
	controls.cancel = new("ButtonControl", nil, { 45, 70, 80, 20 }, tr("Cancel"), function()
		main:ClosePopup()
	end)
	main:OpenPopup(370, 100, skillSetName and tr("Rename Skill Set") or tr("Set Name"), controls, "save", "edit", "cancel")
end

function SkillSetListClass:GetRowValue(column, index, skillSetId)
	local skillSet = self.skillsTab.skillSets[skillSetId]
	if column == 1 then
		local title = skillSet.title or "Default"
		return skillSetId == self.skillsTab.activeSkillSetId and formatUI("%s  ^9(Current)", title) or title
	end
end

function SkillSetListClass:OnOrderChange()
	self.skillsTab.modFlag = true
end

function SkillSetListClass:OnSelClick(index, skillSetId, doubleClick)
	if doubleClick and skillSetId ~= self.skillsTab.activeSkillSetId then
		self.skillsTab:SetActiveSkillSet(skillSetId)
		self.skillsTab:AddUndoState()
	end
end

function SkillSetListClass:OnSelDelete(index, skillSetId)
	local skillSet = self.skillsTab.skillSets[skillSetId]
	if #self.list > 1 then
		main:OpenConfirmPopup(tr("Delete Skill Set"),
			formatUI("Are you sure you want to delete '%s'?", skillSet.title or "Default"), tr("Delete"), function()
				self.skillsSetService:DeleteSkillSet(skillSetId, index)

				self.selIndex = nil
				self.selValue = nil
			end)
	end
end

function SkillSetListClass:OnSelKeyDown(index, skillSetId, key)
	if key == "F2" then
		self:RenameSkillSet(skillSetId)
	end
end
