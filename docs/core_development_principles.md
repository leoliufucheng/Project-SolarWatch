# 📜 SolarWatch 开发核心准则 (Core Development Principles)

## 1. 全球化优先 (Global-First / I18n)
- **禁止硬编码：** 严禁在 UI 渲染层直接写入中文或英文文本。
- **字典驱动：** 所有 UI 文字必须存储在全局 `LANGS` 字典中。
- **同步开发：** 任何新功能模块（如 Sprint 5 的新图表）在开发时，必须同步提供中文和 English 两个版本的文案，并确保 `st.session_state.lang` 切换逻辑完整覆盖。

## 2. 物理隔离与安全 (Security & Isolation)
- **静态读取：** 生产环境代码禁止包含任何 LLM (Gemini) 的实时调用逻辑，必须保持静态数据读取架构。
- **隐私脱敏：** 所有展示给用户的原始评论必须经过 `mask_pii` 函数脱敏。

## 3. 架构一致性 (Architectural Consistency)
- **统一数据源：** 保持 `load_data()` 的集中化，所有页面共享经过脱敏和处理后的统一 DataFrame。

## 4. 🎨 UI 视觉一致性规范 (Sidebar & Layout)
- **标题统一化：** 侧边栏所有功能模块的标题必须使用 `st.sidebar.markdown("### 🏷️ 标题")` 格式。
- **组件标签隐藏：** 在使用 `st.sidebar.radio` 或 `st.sidebar.selectbox` 等组件时，必须设置 `label_visibility="collapsed"`。严禁直接使用组件自带的 label 作为标题，以确保垂直间距和字号的严格统一。
- **国际化强约束 (I18n First)：**
  - 任何新增的 UI 文本（包括 Markdown 标题、组件内部选项、提示信息）必须进入 `LANGS` 字典。
  - 代码中禁止出现任何非变量引用的字符串（如 `st.write("追踪版本")` 是违规的，必须是 `st.write(L["tracking"])`）。
- **模块化分割：** 侧边栏不同功能组之间建议使用 `st.sidebar.markdown("---")` 进行视觉隔离。
