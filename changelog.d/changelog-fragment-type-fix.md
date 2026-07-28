---
type: fix
scope: changelog
---
修正 `changelog.d/` 內 19 個既有（早於本次升版 PR 即存在）不合法 fragment：18 個缺 YAML frontmatter（直接沿用手寫 CHANGELOG.md 區段格式，含 `### Changed`/`### Added`/`### Fixed` 標題與條列 `-` 前綴，`collate` 會在 `parse_fragment()` 階段就對第一個命中的檔案拋出 `FragmentError` 而擋住整個 release）、另 1 個（`48-project-policy-manifest.md`）宣告 `type: chore`（非法 type，會在 `render_section()` 階段拋錯）。逐檔依原有 `### <Section>` 標題或內容語意，改標成 `change`/`feat`/`fix` 之一（合法 type 僅 `change`/`deprecate`/`feat`/`fix`/`perf`/`refactor`/`remove`/`security`），移除多餘的 `### <Section>` 標題與條列 `-` 前綴（`render_section()`/`_bullet()` 會依 `type` 自動分節與加 bullet，原標題／前綴屬冗餘結構、非描述內容，內文文字本身逐字未動）；能從檔名數字前綴與內文自身 `#N` 對應者一併補 `issue:` frontmatter。已以 `policy_check.changelog.collate` 對 19 個 fragment 乾跑驗證可正確產出分節後的 Keep-a-Changelog 區段。
