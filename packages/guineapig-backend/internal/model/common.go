package model

// MaxListLimit 未指定分页时的 List 硬上限，防止 PageSize=0 时全表扫描。
const MaxListLimit = 1000
