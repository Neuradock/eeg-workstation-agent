# NeuraDock EEG Skill for Kimi

NeuraDock EEG development guidance and a local Python analysis toolkit for
Kimi Code. This integration provides an Agent Skill (`SKILL.md`, references,
and scripts). It does not include the Codex MCP bridge or a Kimi plugin manifest.

版本：`0.1.0-beta`。适合使用自然语言协助读取 EEG、检查信号质量、分析
Alpha / PSD / 频段功率，以及开发仿真、回放和 BCI 原型。

## 下载

- [ZIP 技能包](https://github.com/Neuradock/eeg-workstation-agent/raw/refs/heads/main/integrations/kimi/downloads/neuradock-eeg-0.1.0-beta.zip)
- [.skill 技能包](https://github.com/Neuradock/eeg-workstation-agent/raw/refs/heads/main/integrations/kimi/downloads/kimi_neuradock-eeg-0.1.0-beta.skill)
- [校验值](downloads/SHA256SUMS.txt)
- [完整技能源码](skills/neuradock-eeg)

`.skill` 和 `.zip` 是相同内容的 ZIP 容器，解压后包含 `neuradock-eeg/`。
不同 Kimi 产品的导入界面不同。本说明验证的是 Kimi Code CLI 的技能目录
加载方式，不保证普通聊天窗口上传附件就会安装技能。

## 使用方法：Kimi Code CLI

先安装并配置好 [Kimi Code](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)。
以下从仓库加载技能，不修改你的全局技能目录。

```bash
git clone https://github.com/Neuradock/eeg-workstation-agent.git
cd eeg-workstation-agent
kimi --skills-dir ./integrations/kimi/skills
```

在启动的新会话中输入：

```text
/skill:neuradock-eeg
```

也可以将 ZIP 解压到自己选定的 `skills` 目录，保持结构为
`skills/neuradock-eeg/SKILL.md`，然后运行 `kimi --skills-dir <skills目录>`。
参数接收的是包含各个技能文件夹的父目录。

需要跨项目使用时，可将完整 `neuradock-eeg` 文件夹放入
`~/.agents/skills/`。若同名目录已存在，先比较版本并保留自己的修改。
该路径是 Kimi 官方文档支持的通用技能目录。各版本的 Kimi 专属路径不同，
优先使用上面的显式目录参数。

## 运行配套分析脚本

阅读技能不需要安装科学计算依赖。运行 Python 脚本时使用独立虚拟环境，
建议 Python 3.11 或 3.12。

Windows PowerShell，在仓库根目录：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r integrations/kimi/skills/neuradock-eeg/requirements.txt
.\.venv\Scripts\python.exe integrations/kimi/skills/neuradock-eeg/scripts/neuradock_toolkit.py parse C:/data/recording.txt
.\.venv\Scripts\python.exe integrations/kimi/skills/neuradock-eeg/scripts/neuradock_toolkit.py qc C:/data/recording.txt --json quality.json
```

macOS / Linux，在仓库根目录：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r integrations/kimi/skills/neuradock-eeg/requirements.txt
.venv/bin/python integrations/kimi/skills/neuradock-eeg/scripts/neuradock_toolkit.py parse /path/to/recording.txt
.venv/bin/python integrations/kimi/skills/neuradock-eeg/scripts/neuradock_toolkit.py qc /path/to/recording.txt --json quality.json
```

把示例路径替换为自己的文件。`bands` 和 `alpha` 命令的用法相同。
多试次 NPY 文件需要 `--trial 1` 等明确选择，试次编号从 1 开始。
不要把整批试次连接后过滤，也不要把第一个试次当作整批结果。

## 第一个开发任务

尚无设备时，先使用 [公开数据](https://github.com/Neuradock/eeg-workstation-data)，
或让 Kimi 生成明确标记的仿真数据。

```text
/skill:neuradock-eeg 请读取我提供的 NeuraDock 录制文件，先报告通道、样本数、
坏行数量与信号质量。使用本项目 .venv 中的 Python，不修改原始文件。
仅在质量允许时分析后部 Alpha，输出 JSON，并说明被排除的数据。
```

```text
/skill:neuradock-eeg 创建一个 Alpha 可视化应用，先实现仿真和文件回放模式。
采用 4 秒窗口、1 秒步长，先检查质量再显示特征；提供启动说明和测试。
```

## 数据配置与质量门控

- 默认软件顺序：`CP5, CP6, PO3, PO4, O1, Oz, O2`，250 Hz，单位 µV。
- USB 每行 1 个样本，蓝牙每行 5 个样本，均包含保留字段。
- 蓝牙坏包整包排除，非有限 EEG 数值不作为有效样本。
- CLI 在未滤波样本上检查质量，以保留工频和幅度异常证据。
- `bands` 要求整段通过 QC 且无拒绝段，避免将不连续的有效段拼接计算 PSD。
- `alpha` 使用同一时间轴上的原始窗口作质量门控。出现坏行造成的数据缺口时，
  CLI 暂停特征分析，要求先处理数据完整性问题。
- 辅助函数接受数组；单独调用时须明确数组的预处理状态和质量检查阶段。

这是保守的工程门控，不是电极阻抗测量或医学判定。离线 `filtfilt`
不能直接用于需要因果性的实时反馈。原始文件只读，输出文件由使用者指定。

## 验证与版本

见 [发布说明与验证范围](RELEASE.md)。代码测试不等同于 Kimi 模型端到端效果
验证，也不等同于真人设备联调。LLM 会话使用使用者自己的 Kimi 配置，
本包不包含 API 密钥、账号信息或 EEG 录制。

重新打包与测试：

```bash
python -m pytest tests/test_kimi_skill.py
python integrations/kimi/build_package.py
```

软件许可随包提供，采用本仓库的 [MIT License](../../LICENSE)。
