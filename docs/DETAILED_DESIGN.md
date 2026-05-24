# trade-trend-kit Detailed Design

## 1. Background

`trade-trend-kit` is a local Python service for collecting recent X posts from selected finance accounts, analyzing newly collected posts with an OpenAI-compatible large language model, and saving daily investment-reference reports for later delivery to social platforms or apps.

The first version focuses on a reliable local workflow:

- Read target accounts from `config/x.json`.
- Fetch each enabled account every 15 minutes.
- Use Twikit to collect the latest 10 posts per account.
- Persist raw and normalized tweet data as local JSON files.
- Analyze only newly discovered tweets.
- Generate Chinese reports while preserving English source summaries.
- Save account-level and daily reports for future push services.

## 2. Confirmed Product Decisions

| Topic | Decision |
| --- | --- |
| Storage | Local JSON files for MVP. No database in the first version. |
| LLM provider | OpenAI-compatible chat/completions API. |
| Report language | Chinese by default, with English source summaries retained. |
| Analysis cadence | Every 15 minutes, analyze only newly collected tweets. |
| File naming | Use `market_category_account` in file names. |
| Future delivery | Reserve report output format for social platform and app push services. |

## 3. Goals and Non-Goals

### 3.1 Goals

- Provide a repeatable local job that can run continuously.
- Keep account configuration simple and editable.
- Make downloaded tweet data auditable and reusable.
- Avoid duplicate analysis across scheduled runs.
- Produce structured reports that can be consumed by future delivery services.
- Keep external service credentials out of git.
- Keep modules replaceable so storage, X fetching, LLM analysis, and publishing can evolve independently.
- Define stable internal data models so future features do not depend on third-party SDK object shapes.

### 3.2 Non-Goals for MVP

- No database storage.
- No web dashboard.
- No automated trading.
- No investment recommendation execution.
- No push service implementation in MVP.
- No multi-node distributed scheduler.

## 4. Architecture Principles

The project should follow a modular, replaceable, and extensible architecture from the first version. The MVP may be small, but its boundaries should be clear enough to support continuous improvement.

### 4.1 Core Principles

- **Single Responsibility Principle**: each module owns one reason to change. For example, `x_client` handles X access, `tweet_store` handles tweet persistence, and `analyzer` handles LLM analysis.
- **Dependency Inversion**: orchestration code depends on internal interfaces or protocols, not concrete SDKs such as Twikit or a specific LLM provider.
- **Open/Closed Principle**: new storage backends, LLM providers, publishers, and analysis strategies should be added by implementing interfaces, not rewriting the scheduler.
- **Stable Domain Models**: internal models should be project-owned Pydantic models. Third-party SDK objects should be converted at the boundary.
- **Idempotency First**: repeated scheduled runs should not duplicate files, reports, or LLM calls.
- **Configuration Over Code Changes**: account lists, intervals, model settings, and feature toggles should be controlled through config or environment variables.
- **Fail Softly Per Account**: one failing account, provider, or report should not stop the entire scheduled job.
- **Observable by Default**: module boundaries should emit clear logs and structured errors to simplify future operations.

### 4.2 Layering

```text
CLI / Scheduler Layer
    |
Application Service Layer
    |
Domain Models and Ports
    |
Infrastructure Adapters
```

Layer responsibilities:

- **CLI / Scheduler Layer**: parses commands and triggers application use cases.
- **Application Service Layer**: coordinates fetching, deduplication, analysis, report generation, and state updates.
- **Domain Models and Ports**: defines stable data models and abstract capabilities used by the application.
- **Infrastructure Adapters**: implements ports using Twikit, local JSON files, OpenAI-compatible APIs, and future push channels.

The upper layers should not import Twikit, OpenAI SDK clients, or file layout details directly.

## 5. High-Level Architecture

```text
config/x.json
    |
    v
Scheduler
    |
    v
Fetch Job
    |
    +--> XClient(Twikit)
    |       |
    |       +--> X / Twitter
    |
    +--> TweetStore
    |       |
    |       +--> data/raw_tweets
    |       +--> data/normalized_tweets
    |       +--> data/runtime/state.json
    |
    +--> Analyzer(OpenAI-compatible LLM)
    |       |
    |       +--> Account incremental report
    |
    +--> ReportStore
            |
            +--> data/reports/{date}/accounts
            +--> data/reports/{date}/daily_report.*
            +--> data/reports/{date}/publish/publish_payload.*
```

The scheduler reads the latest config before every run. This allows adding, disabling, or editing accounts without restarting the service.

## 6. Module and Interface Design

### 6.1 Proposed Package Layout

```text
src/trade_trend_kit/
  __init__.py
  main.py
  cli.py
  app/
    __init__.py
    fetch_job.py
    report_job.py
    services.py
  domain/
    __init__.py
    models.py
    ports.py
    errors.py
  infra/
    __init__.py
    x/
      __init__.py
      twikit_client.py
    llm/
      __init__.py
      error_archive.py
      openai_compatible.py
      prompts.py
    storage/
      __init__.py
      json_state_store.py
      json_tweet_store.py
      json_report_store.py
    publishing/
      __init__.py
      noop_publisher.py
      payloads.py
  config.py
  scheduler.py
  logging_config.py
  utils/
    __init__.py
    env.py
    filenames.py
    json_io.py
    report_rendering.py
    time.py
```

This structure separates domain logic from infrastructure adapters. It is slightly more structured than a tiny MVP needs, but it prevents early coupling and makes later growth calmer.

### 6.2 Domain Ports

`domain/ports.py` should define interfaces using `typing.Protocol`. Application services depend on these ports.

```python
from typing import Protocol

class XPostClient(Protocol):
    async def fetch_latest_posts(self, account: AccountConfig, limit: int) -> FetchResult:
        ...

class TweetRepository(Protocol):
    async def save_raw(self, batch: RawTweetBatch) -> None:
        ...

    async def save_normalized(self, tweets: list[NormalizedTweet]) -> None:
        ...

class StateRepository(Protocol):
    async def load(self) -> RuntimeState:
        ...

    async def save(self, state: RuntimeState) -> None:
        ...

class TweetAnalyzer(Protocol):
    async def analyze_account_tweets(
        self,
        account: AccountConfig,
        tweets: list[NormalizedTweet],
    ) -> AccountIncrementalReport:
        ...

class ReportRepository(Protocol):
    async def save_account_report(self, report: AccountIncrementalReport) -> None:
        ...

    async def save_daily_report(self, report: DailyReport) -> None:
        ...

class ReportPublisher(Protocol):
    async def publish_daily_report(self, payload: PublishPayload) -> PublishResult:
        ...
```

### 6.3 Adapter Mapping

| Capability | Port | MVP Adapter | Future Adapters |
| --- | --- | --- | --- |
| X fetching | `XPostClient` | `TwikitXPostClient` | `TwscrapeXPostClient`, official API client, mock client |
| Tweet storage | `TweetRepository` | `JsonTweetRepository` | SQLite, Postgres, S3, object storage |
| Runtime state | `StateRepository` | `JsonStateRepository` | SQLite, Redis, Postgres |
| LLM analysis | `TweetAnalyzer` | `OpenAICompatibleAnalyzer` | local model, Anthropic-compatible adapter, rule-based analyzer |
| Reports | `ReportRepository` | `JsonReportRepository` | database-backed reports, blob storage |
| Publishing | `ReportPublisher` | `NoopReportPublisher` | Telegram, Feishu, email, app backend, social platform publisher |

### 6.4 Application Services

Application services should contain orchestration logic but no provider-specific code.

Recommended services:

- `FetchAndAnalyzeJob`: one scheduled or one-shot run across all enabled accounts.
- `AccountFetchService`: fetch and normalize one account.
- `IncrementalAnalysisService`: select unanalyzed tweets and call analyzer.
- `DailyReportService`: aggregate account reports into daily report.
- `StateService`: safe state update helpers.

The service layer should be easy to test with fake ports.

### 6.5 Dependency Assembly

Concrete adapters should be created in one composition root, such as `main.py` or `app/services.py`.

Example:

```python
def build_fetch_job(settings: Settings) -> FetchAndAnalyzeJob:
    x_client = TwikitXPostClient(settings.twikit)
    tweet_repo = JsonTweetRepository(settings.paths)
    state_repo = JsonStateRepository(settings.paths.state_file)
    analyzer = OpenAICompatibleAnalyzer(settings.llm)
    report_repo = JsonReportRepository(settings.paths)
    publisher = NoopReportPublisher()
    return FetchAndAnalyzeJob(
        x_client=x_client,
        tweet_repo=tweet_repo,
        state_repo=state_repo,
        analyzer=analyzer,
        report_repo=report_repo,
        publisher=publisher,
    )
```

This keeps replacements localized. For example, moving from JSON to SQLite should mainly affect the composition root and storage adapter implementation.

### 6.6 Extension Rules

When adding new capabilities:

- Add or reuse a domain port first.
- Keep third-party SDK imports inside `infra/`.
- Convert external data into domain models at the boundary.
- Add unit tests using fake ports before integration tests.
- Avoid passing raw dictionaries across module boundaries after config/model parsing.
- Avoid letting scheduler code decide business behavior; delegate to application services.

## 7. Runtime Workflow

### 7.1 Startup

1. Load environment variables from `.env`.
2. Load runtime settings and account list from `config/x.json`.
3. Initialize logging.
4. Initialize Twikit client.
5. Load Twikit cookies from `data/runtime/cookies.json` if available.
6. Start scheduler with a 15-minute interval.
7. Execute the first fetch job immediately unless disabled by CLI options.

### 7.2 Scheduled Fetch Job

1. Acquire a process-level job lock.
2. Reload `config/x.json`.
3. Read `data/runtime/state.json`.
4. For each enabled account:
   - Resolve the X user by `account`.
   - Fetch the latest 10 tweets.
   - Save raw Twikit payload.
   - Normalize tweets into internal schema.
   - Compare tweet IDs against state.
   - Persist only newly discovered tweets for analysis.
   - Run LLM analysis for new tweets.
   - Save account-level report fragments.
   - Update account state.
5. Merge account-level fragments into the current day's daily report.
6. Release the job lock.

If one account fails, the job records the error and continues with the next account.

## 8. Configuration Design

### 8.1 `config/x.json`

```json
{
  "timezone": "Asia/Shanghai",
  "fetch_interval_minutes": 15,
  "tweet_limit": 10,
  "analysis_language": "zh-CN",
  "preserve_english_summary": true,
  "accounts": [
    {
      "account": "example_user",
      "display_name": "Example Analyst",
      "enabled": true,
      "market": "US_STOCK",
      "category": "macro",
      "region": "US",
      "tags": ["macro", "fed", "nasdaq"],
      "priority": 1,
      "watch_symbols": ["SPY", "QQQ", "NVDA"],
      "notes": "Macro and US equity commentary"
    }
  ]
}
```

### 8.2 Account Fields

| Field | Required | Description |
| --- | --- | --- |
| `account` | Yes | X screen name without `@`. |
| `display_name` | No | Human readable name for reports. |
| `enabled` | Yes | Whether this account is included in scheduled fetches. |
| `market` | Yes | Market dimension used in file names and report grouping. Example: `US_STOCK`, `A_SHARE`, `CRYPTO`. |
| `category` | Yes | Account category used in file names and grouping. Example: `macro`, `tech`, `crypto`, `options`. |
| `region` | No | Geographic focus. |
| `tags` | No | Additional report classification tags. |
| `priority` | No | Lower number means higher priority during future push ranking. |
| `watch_symbols` | No | Symbols that should receive extra attention during analysis. |
| `notes` | No | Operator notes, not used as source truth. |

### 8.3 Environment Variables

`.env.example` should include:

```bash
X_USERNAME=
X_EMAIL=
X_PASSWORD=
TWIKIT_COOKIES_PATH=data/runtime/cookies.json

LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4.1-mini
LLM_TIMEOUT_SECONDS=60
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=

LOG_LEVEL=INFO
LOG_FILE=logs/trade-trend-kit.log
```

The implementation should support cookie-only mode after the first successful login.

## 9. File Storage Design

### 9.1 Directory Layout

```text
data/
  raw_tweets/
    2026-05-22/
      US_STOCK_macro_example_user.json
  normalized_tweets/
    2026-05-22/
      US_STOCK_macro_example_user.json
  reports/
    2026-05-22/
      accounts/
        us_stock_macro_example_user.latest.json
        US_STOCK_macro_example_user.latest.md
        us_stock_macro_example_user.history.json
        archive/
      daily_report.json
      daily_report.md
      daily_report.history.json
      archive/
      publish/
        publish_payload.json
        publish_payload.md
        publish_payload.txt
        publish_payload.history.json
        archive/
      errors/
        us_stock_macro_example_user_20260522223100000000_123_json_repair_failed.json
  runtime/
    cookies.json
    state.json
logs/
  trade-trend-kit.log
```

### 9.2 File Name Rule

Canonical account file key:

```text
{market}_{category}_{account}
```

Rules:

- Convert to lowercase for file names.
- Replace unsafe characters with `_`.
- Preserve account casing inside JSON content.
- Example: `US_STOCK_macro_StockMKTNewz` becomes `us_stock_macro_stockmktnewz`.

### 9.3 Write Strategy

All JSON writes should use atomic writes:

1. Write to `{target}.tmp`.
2. Flush and close.
3. Rename to the target path.

This prevents corrupted files if the process exits during a write.

## 10. Data Models

### 10.1 Normalized Tweet

```json
{
  "tweet_id": "1234567890",
  "account": "example_user",
  "display_name": "Example Analyst",
  "user_id": "987654321",
  "created_at": "2026-05-22T10:15:00+08:00",
  "text": "Original tweet text",
  "english_summary": "Short English summary of the original post.",
  "lang": "en",
  "url": "https://x.com/example_user/status/1234567890",
  "metrics": {
    "reply_count": 0,
    "retweet_count": 0,
    "favorite_count": 0,
    "view_count": null
  },
  "account_meta": {
    "market": "US_STOCK",
    "category": "macro",
    "region": "US",
    "tags": ["macro", "fed"],
    "watch_symbols": ["SPY", "QQQ"]
  },
  "fetched_at": "2026-05-22T22:30:00+08:00"
}
```

`english_summary` may be generated during analysis rather than collection. If a tweet is already English, it should still be a concise summary instead of duplicating full text.

### 10.2 Runtime State

`data/runtime/state.json`:

```json
{
  "accounts": {
    "example_user": {
      "user_id": "987654321",
      "last_fetch_at": "2026-05-22T22:30:00+08:00",
      "last_success_at": "2026-05-22T22:30:00+08:00",
      "seen_tweet_ids": ["1234567890"],
      "analyzed_tweet_ids": ["1234567890"],
      "last_error": null,
      "consecutive_failures": 0
    }
  }
}
```

State is the source of truth for incremental analysis. A tweet is sent to the LLM only if its `tweet_id` is not in `analyzed_tweet_ids`.

### 10.3 Account Incremental Report

```json
{
  "report_id": "2026-05-22T22:30:00+08:00_example_user",
  "date": "2026-05-22",
  "account": "example_user",
  "market": "US_STOCK",
  "category": "macro",
  "new_tweet_count": 3,
  "source_tweet_ids": ["123", "124", "125"],
  "english_source_summaries": [
    {
      "tweet_id": "123",
      "summary": "The author expects rate cuts to be delayed."
    }
  ],
  "chinese_report": {
    "summary": "该账号新增推文主要关注降息预期延后。",
    "market_direction": "中性偏空",
    "key_themes": ["利率", "美股估值", "科技股"],
    "mentioned_symbols": ["SPY", "QQQ"],
    "stock_watchlist": [
      {
        "symbol": "QQQ",
        "direction": "谨慎关注",
        "reason": "利率预期变化可能影响成长股估值。",
        "confidence": "medium",
        "risk": "单一账号观点，需结合更多数据验证。"
      }
    ],
    "risk_notes": [
      "内容仅为信息整理，不构成投资建议。"
    ]
  },
  "created_at": "2026-05-22T22:31:00+08:00"
}
```

### 10.4 Daily Report

```json
{
  "date": "2026-05-22",
  "timezone": "Asia/Shanghai",
  "report_count": 8,
  "source_accounts": ["example_user"],
  "source_tweet_ids": ["123", "124", "125"],
  "market_overview": "今日新增财经推文整体偏谨慎。",
  "consensus_themes": ["AI", "利率", "美元流动性"],
  "conflicting_views": ["部分账号看多科技股，部分账号提示估值压力。"],
  "candidate_symbols": [
    {
      "symbol": "NVDA",
      "market": "US_STOCK",
      "direction": "关注",
      "reason": "多个账号提到 AI 资本开支延续。",
      "confidence": "medium",
      "risks": ["估值高", "财报波动"]
    }
  ],
  "risk_events": ["FOMC", "CPI"],
  "disclaimer": "本报告由公开信息自动整理，仅供研究参考，不构成投资建议。",
  "updated_at": "2026-05-22T22:35:00+08:00"
}
```

## 11. Twikit Integration Design

Twikit should be implemented as an adapter behind the `XPostClient` port so the rest of the project does not depend directly on Twikit object shapes.

Expected responsibilities:

- Initialize async Twikit client.
- Load existing cookies.
- Login and save cookies when needed.
- Resolve screen name to user ID.
- Fetch latest tweets for a user.
- Convert Twikit exceptions into project-level errors.

Adapter API:

```python
class TwikitXPostClient:
    async def fetch_latest_posts(
        self,
        account: AccountConfig,
        limit: int,
    ) -> FetchResult:
        ...
```

Twikit documentation shows an async client workflow with cookie persistence and user timeline fetching. The design should use those features instead of repeatedly logging in.

Reference: [Twikit documentation](https://twikit.readthedocs.io/en/latest/twikit.html).

## 12. LLM Analysis Design

### 12.1 Provider

Use an OpenAI-compatible HTTP client behind the `TweetAnalyzer` port. The current MVP implementation calls `/chat/completions` through a small stdlib JSON transport so Step 10 adds no new runtime dependency.

The transport is injectable, so a later iteration can replace it with:

- Official OpenAI Python SDK configured with `base_url`.
- `httpx` against `/chat/completions`.
- A local-model adapter that still implements `TweetAnalyzer`.

### 12.2 Prompt Requirements

The account-level prompt must ask the model to:

- Summarize each source tweet in English.
- Generate the main report in Chinese.
- Extract market direction.
- Extract key themes.
- Extract mentioned symbols.
- Generate stock watchlist references only when supported by source text.
- Include risk notes and uncertainty.
- Return strict JSON.
- Avoid inventing tickers not supported by the tweets.

### 12.3 Incremental Analysis

Only tweets missing from `analyzed_tweet_ids` should be included in an account analysis request.

If no new tweets exist for an account:

- Do not call the LLM.
- Do not create a new account report.
- Still update `last_fetch_at` and `seen_tweet_ids`.

### 12.4 Output Repair

If the LLM returns invalid JSON:

1. Retry once with a JSON repair prompt.
2. If still invalid, raise `AnalysisError`; the current fetch cycle records the account failure and does not mark tweets analyzed.
3. Save the raw response and repair response to an error archive file under:

```text
data/reports/{date}/errors/{market_category_account}_{timestamp}_{tweet_ids}_{stage}.json
```

4. Do not include API keys, cookies, request headers, or passwords in the archive.
5. Do not mark those tweets as analyzed.

## 13. Scheduling Design

Use `APScheduler` with `AsyncIOScheduler`.

Default schedule:

```text
interval: 15 minutes
timezone: Asia/Shanghai
max_instances: 1
coalesce: true
```

Behavior:

- `max_instances=1` prevents overlapping jobs.
- `coalesce=true` merges delayed runs if the process was busy.
- The job should also maintain an internal async lock for safety.
- The scheduler reloads `config/x.json` before every cycle.
- If `fetch_interval_minutes` or `timezone` changes, the scheduler reschedules the interval job after the current cycle.

CLI commands:

```bash
trade-trend-kit run --fake
trade-trend-kit run --twikit --llm
trade-trend-kit fetch-once --fake
trade-trend-kit fetch-once --twikit --llm
trade-trend-kit validate-config
```

## 14. Error Handling

| Scenario | Handling |
| --- | --- |
| Config invalid | Stop startup or skip invalid account in non-strict mode. |
| Cookies missing | Attempt login if credentials exist. |
| Login failed | Stop job and log actionable error. |
| X rate limit | Back off, mark account failure, continue next account. |
| Account not found | Mark account error and continue. |
| No new tweets | Skip LLM call. |
| LLM timeout | Save error, do not mark tweets analyzed. |
| Invalid LLM JSON | Retry once, archive raw and repair responses, raise `AnalysisError`, record account failure, and do not mark tweets analyzed. |
| File write failure | Log critical error and keep state unchanged for affected account. |

## 15. Logging and Observability

The current implementation initializes console logging from `LOG_LEVEL` and can
also write to `LOG_FILE` or the CLI `--log-file` option. Logging is configured
by the `run` and `fetch-once` commands after loading the selected `.env` file,
so local diagnostics can be controlled without code changes.

Important log events:

- Service startup and shutdown.
- Config reload summary.
- Per-account fetch start/end.
- Number of tweets fetched.
- Number of new tweets detected.
- LLM call start/end.
- LLM chat/completions request duration.
- LLM invalid JSON repair attempt and archive path.
- Report files written.
- Rate limit and authentication failures.
- Fetch cycle duration and summary.

Do not log:

- Passwords.
- API keys.
- Full cookies.
- Full request headers.

Step 14 implementation details:

- `logging_config.configure_logging` supports console logging plus optional file logging.
- `fetch-once` and `run` accept `--log-level` and `--log-file`.
- `FetchAndAnalyzeJob` logs cycle start/end, per-account fetch/analyze events, skips, failures, and daily report writes.
- `JsonReportRepository` logs report and publish payload paths after successful writes.
- `OpenAICompatibleAnalyzer` logs analysis lifecycle, request duration, repair attempts, and archive paths.
- `JsonLLMErrorArchive` writes invalid response records to `data/reports/{date}/errors/`.

## 16. Security and Compliance Notes

- `.env`, cookies, runtime state, logs, and data files should not be committed unless explicitly intended.
- The project should include a clear disclaimer that reports are informational and not investment advice.
- X access may be subject to platform rules and rate limits. The implementation should be conservative with request frequency and retries.

## 17. Future Push Service Integration

The MVP should not send reports, but report storage should be push-friendly. Publishing is represented by a `ReportPublisher` port, a channel-neutral `PublishPayload`, and `NoopReportPublisher` as the MVP adapter.

Current push-ready files:

```text
data/reports/{date}/publish/publish_payload.json
data/reports/{date}/publish/publish_payload.md
data/reports/{date}/publish/publish_payload.txt
data/reports/{date}/publish/publish_payload.history.json
data/reports/{date}/publish/archive/*
```

Recommended future push interface:

```python
class ReportPublisher:
    async def publish_daily_report(self, payload: PublishPayload) -> PublishResult:
        ...
```

Future channels may include:

- Telegram bot.
- Discord webhook.
- WeChat/enterprise WeChat.
- Feishu/Lark.
- Email.
- Mobile app backend API.
- Social platform scheduled posting.

To support these channels, publish payloads include structured sections, Markdown, plain text, hashtags, source accounts, source tweet IDs, candidate symbols, risks, and a disclaimer.

## 18. Testability Strategy

Testing should reinforce modular design.

Recommended test levels:

- **Unit tests**: config parsing, file naming, state deduplication, report aggregation, LLM JSON parsing.
- **Service tests**: run `FetchAndAnalyzeJob` with fake X client, local JSON repositories, and fake analyzer.
- **Adapter tests**: test JSON repositories against temporary directories.
- **Integration tests**: optional Twikit and LLM tests gated by environment variables so normal CI does not require real credentials.

Current automated suite covers CLI parsing, config validation, domain models, fake end-to-end pipeline, incremental selection, OpenAI-compatible parsing/repair/error archiving, publish payload generation, Markdown rendering, scheduler behavior, JSON storage, tweet normalization, logging setup, and Twikit adapter boundary behavior.

The first implementation should include fakes for key ports:

```python
class FakeXPostClient:
    async def fetch_latest_posts(self, account: AccountConfig, limit: int) -> FetchResult:
        ...

class FakeTweetAnalyzer:
    async def analyze_account_tweets(
        self,
        account: AccountConfig,
        tweets: list[NormalizedTweet],
    ) -> AccountIncrementalReport:
        ...
```

These fakes make future refactors safer and keep business logic testable without network access.

## 19. Implementation Plan

### 19.1 Step-by-Step Delivery Matrix

| 步骤 | 功能增量 | 主要产物 | Review 重点 |
| --- | --- | --- | --- |
| Step 1 | 建立项目骨架、CLI 入口、src 布局 | `pyproject.toml`、`src/trade_trend_kit/`、基础 `README` | 包结构是否清晰，入口是否可扩展，是否避免把业务逻辑塞进入口文件 |
| Step 2 | 建立领域模型、端口、错误类型 | `domain/models.py`、`domain/ports.py`、`domain/errors.py` | 模型是否稳定、端口是否只表达能力不绑定实现、命名是否可长期复用 |
| Step 3 | 加载并校验配置 | `config.py`、`config/x.json`、`config/x.example.json`、`validate-config` | 配置校验是否严格、默认值是否合理、错误信息是否可操作 |
| Step 4 | JSON 本地存储基础设施 | `utils/json_io.py`、`infra/storage/*`、`state.json`、tweet/report 文件落盘 | 文件命名是否满足 `market_category_account`、写入是否原子、重复运行是否幂等 |
| Step 5 | 端到端 fake 流水线 | `infra/fake/*`、`app/fetch_job.py`、`app/report_job.py`、`fetch-once --fake` | 数据流是否闭环、只分析新增推文是否成立、状态和报告是否会重复写入 |
| Step 6 | 增量分析逻辑 | `app/incremental.py`、`FetchAndAnalyzeJob` 状态更新改造、增量单测 | 只分析新增推文是否稳定，分析失败是否不会误标记 `analyzed_tweet_ids`，状态更新是否可测试 |
| Step 7 | 报告生成与归档 | Markdown 渲染、latest/history/archive 报告文件、归档测试 | JSON 与 Markdown 是否同时生成，history/archive 是否幂等，日报是否适合后续推送服务读取 |
| Step 8 | 接入真实 Twikit 适配器 | `infra/x/twikit_client.py` 的真实实现、`fetch-once --twikit`、账号登录/抓取/错误映射 | Twikit 对象是否在边界转换，异常是否归一化，是否只在适配层依赖第三方 SDK |
| Step 9 | Tweet 标准化 | `infra/x/normalizer.py`、Twikit/fake 标准化接入、标准化单测 | 文本清洗、时间转换、URL 补全、指标提取、重复 tweet 去重是否一致 |
| Step 10 | 接入真实 OpenAI-compatible 分析器 | `infra/llm/openai_compatible.py`、`infra/llm/prompts.py` | Prompt 是否约束输出 JSON，是否保留英文摘要，失败重试和坏 JSON 是否可恢复 |
| Step 11 | 计划任务与持续运行 | `scheduler.py`、`run` 命令、周期执行 | 是否 15 分钟调度，是否避免重叠执行，是否支持配置热重载 |
| Step 12 | 发布与推送预留 | `infra/publishing/*`、日报导出格式 | 输出是否适合后续推送，字段是否足够稳定，是否便于不同渠道复用 |
| Step 13 | 文档与设计一致性收口 | `docs/DETAILED_DESIGN.md`、`README.md` | 文档是否准确反映当前接口、命令、文件布局和剩余 backlog |
| Step 14 | 可观测性与错误归档 | 结构化日志、LLM 原始错误响应归档、运行诊断文档 | 失败是否可定位，是否不泄露密钥/cookie，是否不误标记已分析推文 |
| Step 15 | 可选真实集成测试 | gated Twikit/LLM integration tests、首次登录说明 | CI 是否默认离线，真实验证是否有明确环境变量开关 |

当前实现状态：

- Step 1 到 Step 14 已完成。
- MVP 主链路已经具备本地配置、Twikit/fake 抓取、增量分析、报告归档、调度运行、推送预留输出、关键日志和 LLM 错误归档。

### 19.2 Per-step Review Focus

每一步提交前建议按下面几个维度做 Review：

- **边界**：新增代码是否仍然遵守“应用层依赖端口、适配层依赖 SDK”的分层。
- **幂等**：重复执行是否只补充新增数据，不会覆盖掉历史或重复分析。
- **可替换**：fake、Twikit、LLM、存储、发布是否都能独立替换。
- **可测试**：是否能用临时目录和 fake 对象完成单元或端到端测试。
- **可观测**：失败时是否有足够信息定位到账号、日期、文件或上游响应。
- **扩展性**：新增账号、市场分类、报告字段或推送渠道时，是否只需要局部改动。

### 19.3 Existing Phase Plan

### Phase 1: Project Skeleton

- Add `pyproject.toml`.
- Add package under `src/trade_trend_kit`.
- Add config models.
- Add domain models and ports.
- Add `.env.example`.
- Add sample `config/x.json`.
- Add logging setup.

### Phase 2: Local Storage

- Implement file naming utility.
- Implement atomic JSON writes.
- Implement state load/save.
- Implement normalized tweet storage.
- Keep all storage logic behind repository ports.

### Phase 3: Twikit Fetching

- Implement Twikit client wrapper.
- Implement cookie loading and saving.
- Implement per-account latest tweet fetching.
- Convert Twikit objects into domain models at the adapter boundary.
- Add manual `fetch-once` command.

### Phase 4: Incremental Analysis

- Implement OpenAI-compatible analyzer.
- Add account-level prompt template.
- Parse and validate JSON output.
- Save incremental account reports.

### Phase 5: Daily Report Aggregation

- Merge account report fragments.
- Generate `daily_report.json`.
- Generate `daily_report.md`.

### Phase 6: Scheduler

- Add `run` command.
- Schedule job every 15 minutes.
- Add max-instance and lock protection.

### Phase 7: Tests and Documentation

- Unit test config validation.
- Unit test file naming.
- Unit test state-based deduplication.
- Unit test LLM output parsing.
- Unit test application services with fake ports.
- Document first-run login and cookie reuse.

## 20. Acceptance Criteria

- `trade-trend-kit validate-config` validates `config/x.json`.
- `trade-trend-kit fetch-once` fetches enabled accounts and writes JSON files.
- Re-running `fetch-once` without new tweets does not call the LLM again.
- New tweets produce account-level report JSON and Markdown.
- Daily report files are updated under `data/reports/{date}`.
- Push-ready payload files are updated under `data/reports/{date}/publish`.
- The scheduler runs every 15 minutes without overlapping jobs.
- `fetch-once` and `run` can write local diagnostics through `--log-file` or `LOG_FILE`.
- Invalid LLM JSON responses are archived under `data/reports/{date}/errors/` without marking tweets analyzed.
- Secrets and runtime files are ignored by git.
- Application services can be tested without Twikit, real files, or real LLM calls.
- Twikit, JSON storage, LLM analysis, and publishing are replaceable through ports/adapters.

## 21. Open Questions

| Question | Current Decision / Status |
| --- | --- |
| Which OpenAI-compatible provider and model should be the default in `.env.example`? | Default to OpenAI-compatible `https://api.openai.com/v1` with `gpt-4.1-mini`; users can override `LLM_BASE_URL` and `LLM_MODEL`. |
| Should retweets and replies be included, or only original tweets? | Still open. Current Twikit adapter fetches the timeline response and normalizes returned tweets; filtering policy should be added explicitly if needed. |
| Should quote tweets be analyzed together with quoted content when available? | Still open. Current normalizer analyzes available tweet text only; quote expansion can be a future normalizer enhancement. |
| Should daily reports be regenerated after every incremental account report, or only at a fixed end-of-day time? | Current implementation regenerates the daily report after each cycle that produces at least one account report. |
| Should `priority` influence analysis order only, or also future push ranking? | Current implementation uses lower `priority` for account processing order. Future push ranking remains open. |

## 22. Backlog After Step 14

- Step 15: Add gated real integration tests for Twikit and OpenAI-compatible providers, plus first-run login/cookie reuse documentation.
- Future: Decide retweet/reply/quote handling policy and whether `priority` should affect push ranking.
