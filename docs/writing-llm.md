# 写作批改 / 追问用的模型

管的范围：写作页的思维链、小作文仿写、模板写作三处批改，批改卡片下的「追问 AI」，以及右下角的 AI 写作助手。听力精听、精读翻译用的是各自 `prompts/*.yaml` 里的模型，不受这里影响。

## 现在用的

| | 模型 | 走哪条接口 |
|---|---|---|
| 主模型 | `wild/claude-sonnet-5-5` | WildAPI 的 OpenAI 兼容接口 `/v1/chat/completions` |
| 后备 | `gemini-3.8-flash` | WildAPI 的 Gemini 原生接口 |

两个都用同一个 `WILDAPI_API_KEY`，服务器上本来就有。

## 怎么切换

只有一处要改，提示词 yaml 里不再写模型。

- **临时换，不改代码**：在服务器 `.env` 里加一行 `WRITING_LLM_MODEL=<模型>`，执行 `sudo service ielts restart`。删掉这行再重启，就回到默认。
- **长期换**：改 `routers/writing_logic.py` 顶部的 `WRITING_MODEL` 一行，提交、部署。
- 后备模型同理：代码里是 `WRITING_FALLBACK_MODEL`，`.env` 里是 `WRITING_LLM_FALLBACK`。

`<模型>` 能填的值：

| 写法 | 走哪 | 要的 key | 说明 |
|---|---|---|---|
| `wild/claude-sonnet-5-5` | WildAPI（OpenAI 兼容） | `WILDAPI_API_KEY` | 默认：快 |
| `gemini-3.8-flash` | WildAPI（Gemini 原生） | `WILDAPI_API_KEY` | 后备，也是 2026-11 之前的默认 |
| `aihubmix/gemini-4-hydrogen@low` | AIHubMix | `AIHUBMIX_API_KEY` | 盲评质量最好，但出分慢一倍、要单独充值 |
| `aihubmix/gemini-4-hydrogen@medium` | AIHubMix | `AIHUBMIX_API_KEY` | 漏错最少，出分约 11 秒 |
| `deepseek-flash` | DeepSeek 官方 | `DEEPSEEK_API_KEY` | 2026-10 测过：快，但讲错原因的次数约是 Gemini 的 3 倍 |
| `wild/<Wild 上的模型名>` | WildAPI（OpenAI 兼容） | `WILDAPI_API_KEY` | 理论上 Wild 的 Claude / GPT 都能这么填，没逐个测 |

`aihubmix/…@low` 后面的 `@low` 是思考档位（low / medium / high / xhigh）。不写就是 low。

## 出错时会怎样

- **主模型失败就换后备**：主模型照常重试一次。还是失败（余额用完 403、key 没配、5xx、超时、回了空内容），就换后备模型整条重来，页面上看不出区别。如果已经吐出半截再断，不换后备，由页面整条重试，因为半截内容拼不起来。
- **怎么看退回了几次**：`journalctl -u ielts --since today | grep 改用`，每一行是一次退回后备，后面写着原因。
- **Wild 的坑**：WildAPI 把 Claude 的非流式回复转成 OpenAI 格式时会把正文弄丢。它返回 200，content 却是空串，usage 里又记着两百多个输出 token。所以 `wild/` 模型连追问这种非流式调用也走流式，拼起来再返回。
- **思考模型要等更久**：AIHubMix 的 gemini-4-hydrogen 思考关不掉，第一个字之前会闷头想 3 到 28 秒。这条路第一个字前最多等提示词里的 `timeout`（40 秒），其余模型 15 秒没新内容就算卡住。

## 2026-11-15 测试记录

### 方法

- **题目**：
  - `script/bench_writing_cases.json` 里的 27 道批改题：故意埋错的、一字不差的、换个正确说法的。
  - 12 道追问题。
  - 56 句真实作答，来自服务器 2026-10-16 的快照。真实作答只在本地跑，不进仓库。
- **跑法**：`script/bench_writing_llm.py`（`--models` 写法同上表，`--data-dir` 指向快照目录），每题每个模型各跑一次。批改另按线上方式流式调用，记下出第一个字的时间。
- **质量**：三个 AI 评委盲评。每题的几份答案打乱成 X/Y/Z，评委不知道哪份是哪个模型。逐条记四项：讲错原因、把对的判成错、漏掉真错误、分数偏差 ≥1 档。
- **价格**：来自 gptsapi.net、aihubmix.com 当天的公开价目页。每次批改的花费是按实测 token 数估的（输入约 1.8k token）。

### 1. WildAPI 的 gemini-4-hydrogen：基本就是 gemini-3.8-flash，别用

- **答案一模一样**：它答出来的 33 题里，25 题和 gemini-3.8-flash 逐字相同；gemini-3.8-flash 自己跑两遍，也是这 25 题相同。连小毛病都一样，比如列了三处错，总评写「两处」。
- **不像真的 hydrogen**：它接受 `thinkingBudget: 0`。按 Google 的说明，真的 gemini-4-hydrogen 收到这个参数要返回 400。
- **贵一倍**：每百万 token 输入 $1.20 / 输出 $6.00，gemini-3.8-flash 是 $0.60 / $3.00。每次调用还多算约 30 个输入 token。
- **不稳定**：跑了约 30 次之后连续返回 502，约半小时后才恢复。

### 2. AIHubMix 的 gemini-4-hydrogen：质量最好，但慢、贵

55 道批改（三家都答出来的题）加 12 道追问，盲评结果：

| | gemini-3.8-flash | hydrogen low | hydrogen medium |
|---|---|---|---|
| 讲错原因 | 17 | 0 | 1 |
| 把对的判成错 | 12 | 5 | 3 |
| 漏掉真错误 | 26 | 15 | 4 |
| 分数偏差 ≥1 档 | 0 | 0 | 1 |
| 被评为三者中最差 | 39 | 2 | 1 |
| 逐题比 gemini-3.8-flash 更好 / 更差 | — | 45 / 4 | 50 / 3 |
| 追问平均分（满分 5） | 4.00 | 4.67 | 4.83 |
| 批改出第一个字，中位 / P90 | 3.0 / 7.4 秒 | 6.2 / 9.6 秒 | 11.3 / 19.4 秒 |
| 每次批改约 | $0.002 | $0.012 | $0.019 |

- **思考关不掉**：只能用 `reasoning_effort` 选 low / medium / high / xhigh，传 `thinking_budget` 会返回 400，temperature 会被忽略。
- **思考 token 按输出计费**：low 每次思考约 900 token，medium 约 1800 token，所以比标价看上去贵得多。
- **余额很快见底**：大约 137 次调用之后，账户余额用完，开始返回 403 `insufficient_user_quota`。

### 3. 找又快又好的：claude-sonnet-5-5（WildAPI）

用三句批改（一句埋错题、两句真实作答），流式测速度：

| 模型 | 出第一个字 | 整条写完 | JSON 合法 |
|---|---|---|---|
| `wild/claude-sonnet-5-5` | 约 2 秒 | 4–6 秒 | 3/3 |
| `wild/claude-haiku-5-5` | 6–14 秒 | 7–15 秒 | 3/3 |
| `gemini-3.8-flash`（对照） | 约 3 秒 | 约 4 秒 | — |
| `aihubmix/gemini-4-hydrogen@low`（对照） | 约 6 秒 | 约 8 秒 | — |

- **Sonnet**：不先思考，所以快；每次批改约 $0.007（每百万 token $1.60 / $8.00）。抽查结果：埋错题三处错全抓到、解释都对；两道追问答得准确简洁。
- **Haiku**：在 Wild 上反而慢，不考虑。
- **没做完整盲评**：Sonnet 没像上面那样做 55 题盲评，因为额度不多。上线时只确认了抽查结果和页面正常。

### 结论

- **切到 Sonnet**：默认改成 `wild/claude-sonnet-5-5`。出分比原来的 gemini-3.8-flash 还快，不用另开 AIHubMix 账户；出问题自动退回 gemini-3.8-flash。
- **更看重质量时**：在 `.env` 里写 `WRITING_LLM_MODEL=aihubmix/gemini-4-hydrogen@low`（先给 AIHubMix 充值、配 `AIHUBMIX_API_KEY`）。

### 还没做

额度够时，把 Sonnet 补进盲评，和 hydrogen 正面比一次：

```bash
uv run python script/bench_writing_llm.py --models wild/claude-sonnet-5-5 aihubmix/gemini-4-hydrogen@low gemini-3.8-flash --data-dir <真实作答目录>
```
