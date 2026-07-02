# Claude Code / Agent SDK を Amazon Bedrock・Google Vertex AI で運用する

エンタープライズで「データを自社のクラウド境界内に留めたい」「既存のAWS/GCP契約・課金・IAMに載せたい」時の実運用リファレンス。公式仕様（`code.claude.com/docs/en/amazon-bedrock`, `.../google-vertex-ai`）ベース。Academy「Claude with Amazon Bedrock」「Claude with Google Vertex AI」に対応。

> **モデルID・バージョン・既定値は頻繁に変わる。** 本ファイルのIDは記述時点の例。実装時は必ず [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) と各クラウドのModel catalog/Garden、`/status`・`/model` で最新を確認する。

---

## 0. いつ Bedrock/Vertex を選ぶか

| 状況 | 選択 |
|---|---|
| 既に AWS 中心・IAM/課金を AWS に集約したい・データをAWS境界に | **Bedrock** |
| 既に GCP 中心・IAM/課金を GCP に集約したい・データをGCP境界に | **Vertex AI** |
| どちらのクラウド契約も無い・最速で始めたい | Anthropic API 直（[`11`](./11-claude-code-tool-use-and-sdk.md)） |
| 組織で集中管理・監査・上限管理したい | いずれか＋[LLM gateway](https://code.claude.com/docs/en/llm-gateway) |

共通の狙い: **モデル推論を自社のクラウドアカウント内で完結**させ、既存のセキュリティ・調達・可観測性に統合する。Claude Code / Agent SDK のどちらもこの2クラウドをバックエンドにできる。

---

## パート1: Amazon Bedrock

### 前提
- Bedrock有効化済みのAWSアカウント、対象Claudeモデルへのアクセス、適切なIAM権限、（任意で）AWS CLI。
- 初回は **use case 申請**（アカウント毎に1回）: Bedrockコンソール → Model catalog → Anthropicモデル → use caseフォーム。承認は即時。AWS Organizations なら管理アカウントから `PutUseCaseForModelAccess` API で一括。

### 最短: サインインウィザード
`claude` 起動 → ログインで **3rd-party platform → Amazon Bedrock** → 認証方法（`~/.aws`のプロファイル／Bedrock APIキー／アクセスキー／環境の既存資格情報）を選ぶ。ウィザードがregion検出・モデル検証・pinを行い、user settingsの `env` に保存。以後 `/setup-bedrock` で再設定。

### 手動設定（CI・スクリプト配布向け）

**認証（AWS SDK既定の資格情報チェーン）:**
```bash
# A: CLI設定
aws configure
# B: アクセスキー
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...
# C: SSOプロファイル
aws sso login --profile myprofile ; export AWS_PROFILE=myprofile
# E: Bedrock APIキー（フルAWS資格情報不要の簡易認証）
export AWS_BEARER_TOKEN_BEDROCK=your-bedrock-api-key
```

**有効化とregion:**
```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1        # プロファイルにregionが無い/上書きする時
```
region解決順: `AWS_REGION` → `AWS_DEFAULT_REGION` → アクティブプロファイルの `region` → `us-east-1`。`/status` で解決結果を確認。

**モデルpin（複数ユーザー配布では必須）:** aliasの `sonnet`/`opus` は既定に解決され最新に遅れることがある。**特定IDに固定する。** Bedrockはクロスリージョン推論プロファイルID（`us.` プレフィックス、GovCloudは `us-gov.`）を使う。
```bash
export ANTHROPIC_DEFAULT_OPUS_MODEL='us.anthropic.claude-opus-4-8'
export ANTHROPIC_DEFAULT_SONNET_MODEL='us.anthropic.claude-sonnet-4-6'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='us.anthropic.claude-haiku-4-5-20251001-v1:0'
# 単発上書き: export ANTHROPIC_MODEL='us.anthropic.claude-sonnet-4-6'
# アプリ推論プロファイルARNも指定可: export ANTHROPIC_MODEL='arn:aws:bedrock:...:application-inference-profile/...'
```
- 背景タスク（タイトル生成等）はsmall/fastモデルを使うが、BedrockではHaikuが全アカウントで有効とは限らないため既定はprimary。Haikuを使うなら `ANTHROPIC_DEFAULT_HAIKU_MODEL` を有効なIDに。
- 複数バージョンを `/model` に出すなら settings の `modelOverrides` で version→ARN をマッピング。

**IAMポリシー（最小構成）:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "ModelAccess", "Effect": "Allow",
      "Action": ["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream",
                 "bedrock:ListInferenceProfiles","bedrock:GetInferenceProfile"],
      "Resource": ["arn:aws:bedrock:*:*:inference-profile/*",
                   "arn:aws:bedrock:*:*:application-inference-profile/*",
                   "arn:aws:bedrock:*:*:foundation-model/*"] },
    { "Sid": "Marketplace", "Effect": "Allow",
      "Action": ["aws-marketplace:ViewSubscriptions","aws-marketplace:Subscribe"],
      "Resource": "*",
      "Condition": {"StringEquals": {"aws:CalledViaLast": "bedrock.amazonaws.com"}} }
  ]
}
```

**資格情報の自動更新（settings.json）:**
```json
{ "awsAuthRefresh": "aws sso login --profile myprofile",
  "env": { "AWS_PROFILE": "myprofile" } }
```
- `awsAuthRefresh`: 期限切れ検知時のみ実行（`.aws`を変更するSSO系向け、出力は表示）。
- `awsCredentialExport`: セッション開始・再読込ごとに実行、JSON資格情報を直接返す（`.aws`を触れない時。出力は非表示）。

**運用オプション:**
- プロンプトキャッシュ: 既定有効。`DISABLE_PROMPT_CACHING=1` で無効、`ENABLE_PROMPT_CACHING_1H=1` で1時間TTL（課金高）。region非対応だとキャッシュトークンが0のまま。
- 1M context: 対応モデルで `[1m]` をID末尾に付与（ウィザードも選択肢を出す）。
- サービスティア: `ANTHROPIC_BEDROCK_SERVICE_TIER=default|flex|priority`（コスト/レイテンシのトレードオフ）。
- ガードレール: Bedrock Guardrailを作成し `ANTHROPIC_CUSTOM_HEADERS` に `X-Amzn-Bedrock-GuardrailIdentifier`/`Version` を設定。クロスリージョン時はGuardrail側でも有効化。
- 制約: **WebSearchツールはBedrockで使えない**。`/logout` 不可（AWS資格情報管理のため）。Bedrock Invoke API使用（Converse API非対応）。

**Mantleエンドポイント**（ネイティブAnthropic APIシェイプで提供、モデル系列はBedrock標準カタログと別）:
```bash
export CLAUDE_CODE_USE_MANTLE=1 ; export AWS_REGION=us-east-1
claude --model anthropic.claude-haiku-4-5    # anthropic. プレフィクス・バージョン無し
```
Bedrockと併用（`CLAUDE_CODE_USE_BEDROCK=1` も設定）でIDの形により自動振り分け。`/status` に `Amazon Bedrock (Mantle)` 表示。

**トラブルシュート:**
- SSOで認証ループ → `awsAuthRefresh` を外し、手動 `aws sso login` してから起動。
- region/「on-demand throughput未対応」→ 推論プロファイルID指定、`aws bedrock list-inference-profiles --region ...` で確認。
- `/context` のツールトークンが0 → v2.1.196以降に更新。

---

## パート2: Google Vertex AI

### 前提
- 課金有効のGCPプロジェクト、Vertex AI API有効化、対象Claudeモデルへのアクセス、`gcloud` 導入、対象regionのquota。
- **モデルアクセス申請**: [Vertex AI Model Garden](https://console.cloud.google.com/vertex-ai/model-garden) で "Claude" を検索し対象モデルをリクエスト（承認に24-48h）。

### 最短: サインインウィザード（v2.1.98+）
`claude` → **3rd-party platform → Google Vertex AI** → 認証（gcloudのADC／サービスアカウントキー／環境の既存資格情報）。project/region検出・モデル検証・pinをして user settings に保存。以後 `/setup-vertex`。

### 手動設定

**API有効化:**
```bash
gcloud config set project YOUR-PROJECT-ID
gcloud services enable aiplatform.googleapis.com
```

**認証（標準のGoogle Cloud認証 = ADC）:**
```bash
gcloud auth application-default login           # ADC
# or サービスアカウント:
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```
- プロジェクトIDは `ANTHROPIC_VERTEX_PROJECT_ID` を使うが、`GOOGLE_CLOUD_PROJECT`/`GCLOUD_PROJECT`/`GOOGLE_APPLICATION_CREDENTIALS` の資格情報が優先。X.509 Workload Identity Federation にも対応（v2.1.121+）。

**有効化とregion:**
```bash
export CLAUDE_CODE_USE_VERTEX=1
export CLOUD_ML_REGION=global          # global / マルチリージョン(eu,us) / 特定region(us-east5)
export ANTHROPIC_VERTEX_PROJECT_ID=YOUR-PROJECT-ID
# global未対応モデルはリージョン上書き:
export VERTEX_REGION_CLAUDE_HAIKU_4_5=us-east5
export VERTEX_REGION_CLAUDE_4_6_SONNET=europe-west1
```
- モデルの提供はエンドポイント種別（global/マルチ/特定region）で異なる。Model Gardenの "Supported features" で確認。

**モデルpin（複数ユーザー配布では必須）:** Vertexは `@` バージョン付きIDを使う。
```bash
export ANTHROPIC_DEFAULT_OPUS_MODEL='claude-opus-4-8'
export ANTHROPIC_DEFAULT_SONNET_MODEL='claude-sonnet-5'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='claude-haiku-4-5@20251001'
# 単発: export ANTHROPIC_MODEL='claude-opus-4-8'
```
背景タスクのHaiku既定はBedrock同様primaryにフォールバック（Haikuが全projectで有効とは限らないため）。

**IAM:** `roles/aiplatform.user`（`aiplatform.endpoints.predict` を含む）を付与。より厳格にはこの権限だけのカスタムロール。

**資格情報の自動更新（settings.json）:**
```json
{ "gcpAuthRefresh": "gcloud auth application-default login",
  "env": { "ANTHROPIC_VERTEX_PROJECT_ID": "your-project-id" } }
```

**運用オプション:**
- プロンプトキャッシュ: 自動有効。`DISABLE_PROMPT_CACHING=1`／`ENABLE_PROMPT_CACHING_1H=1`。
- 1M context: 対応モデルで `[1m]`。
- **MCP tool search は Vertex で既定オフ**（ツール定義を前ロード）。対応モデル（Sonnet 4.5+/Opus 4.5+）で使うなら `ENABLE_TOOL_SEARCH=true`。旧モデルで有効化すると失敗。
- `/logout` 不可（GCP資格情報管理のため）。

**トラブルシュート:**
- "Could not load the default credentials" → `gcloud auth application-default login` か `GOOGLE_APPLICATION_CREDENTIALS`。
- 404 "model not found" → Model Gardenで Enabled 確認、指定locationでの提供有無を確認（global専用/マルチ専用のモデルがある）。
- 429 → region対応を確認、`CLOUD_ML_REGION=global` に切替で可用性改善。
- quota → Cloud Consoleで確認/増枠申請。

---

## パート3: 共通の実運用ポイント

- **配布前にモデルを必ずpinする。** aliasは既定に解決され、アカウント/projectで未有効なことがある。pinで移行タイミングを制御。起動時チェックでpin更新を促される/フォールバックされる。
- **専用アカウント/プロジェクトを切る。** コスト追跡とアクセス制御が単純になる（両公式の推奨）。
- **Agent SDK / API も同じバックエンドに向けられる。** SDK・Anthropic SDKは Bedrock/Vertex 用の設定（同種のenv/資格情報）で同じモデルを叩ける。自律エージェント（[`13`](./13-advanced-agent-patterns.md)）を自社クラウド内で動かす時はこの構成。
- **ゲートウェイ集約**: 組織で監査・上限・鍵集中管理をするなら [LLM gateway](https://code.claude.com/docs/en/llm-gateway) を挟み、クライアント側認証を無効化してサーバー側で資格情報を注入。
- **コスト/可観測性**: プロンプトキャッシュ（[`04`](./04-tool-selection-matrix.md)）、OpenTelemetry可観測性（[`06`](./06-evaluation-and-iteration.md)・Agent SDK）を組み合わせる。

---

## チェックリスト
- [ ] use case申請/Model Gardenアクセスを済ませた
- [ ] 認証（IAM/SSO/APIキー ・ ADC/サービスアカウント）を選び設定した
- [ ] `CLAUDE_CODE_USE_BEDROCK`/`_VERTEX` とregion/projectを設定した
- [ ] **モデルを特定IDにpin**した（Bedrock=`us.`推論プロファイル / Vertex=`@`バージョン）
- [ ] 最小IAM（Bedrockポリシー / `aiplatform.user`）を付与した
- [ ] プロンプトキャッシュ・1M context・（必要なら）ガードレール/tool searchを設定した
- [ ] 機密データの境界（自社クラウド内完結）とゲートウェイ集約要否を決めた
- [ ] `/status`・`/model` で解決モデル/regionを確認した
