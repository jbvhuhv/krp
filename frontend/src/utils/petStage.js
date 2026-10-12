// 宠物进化形态：同一只宠物随等级呈现「幼年体 → 成长期 → 完全体」三种外观。
// 阈值与标签集中在此，PetAvatar 与各页面共用同一套分档，避免各处漂移。
const PET_STAGE = {
  TEEN_LEVEL: 3,
  ADULT_LEVEL: 6,
}

const PET_STAGE_LABEL = {
  baby: '幼年体',
  teen: '成长期',
  adult: '完全体',
}

export function petStage(level) {
  const lv = Number(level) || 1
  if (lv >= PET_STAGE.ADULT_LEVEL) return 'adult'
  if (lv >= PET_STAGE.TEEN_LEVEL) return 'teen'
  return 'baby'
}

export function petStageLabel(level) {
  return PET_STAGE_LABEL[petStage(level)]
}