# フェーズ4: 成果物テンプレート集

「保存・実行すれば動く」レベルの雛形。案件で確定したツールに対応するものを選び、埋めて使う。

**収録テンプレ**: A システムプロンプト / B 素のSDK(Claude) / C LangGraph(HITL) / D CrewAI / E MCPサーバー / F n8n / G Claude Code拡張 / H 評価テストケース / **I OpenAI Agents SDK(handoffs, Claude可)** / **J RAG(pgvector)** / **K ガードレール** / **L ストリーミング** / **M 可観測性** / **N Docker＋CI評価**。

> **注意**: モデルID・SDKのバージョン・APIの細部は変わる。Claudeを使う場合、Claude Code環境なら `claude-api` スキルで最新のモデルID・料金・パラメータを必ず確認してから確定すること。第三者フレームワーク（LangGraph / CrewAI / OpenAI Agents SDK / pgvector 等）も各公式ドキュメントで現行APIを確認する。このファイルの値はプレースホルダを含む雛形。

---

## テンプレA: システムプロンプト（どのフレームワークでも使う土台）

```
# 役割
あなたは{エージェントの役割を1行で}。

# ゴール
{何を達成したら成功か。定量基準があれば書く}

# 入力として受け取るもの
{入力の形式}

# 出力として返すもの
{出力の形式。JSONなら厳密なスキーマを書く}

# 手順
1. {ステップ1}
2. {ステップ2}
...

# 使ってよいツール
- {ツール名}: {いつ使うか}

# 制約・禁止事項
- {やってはいけないこと}
- 不明な点は推測で埋めず、{確認方法}で確認する
- {機密情報の扱い}

# 出力フォーマット
{厳密な出力形式。例を1つ添える}
```

**コツ**: 「役割・ゴール・手順・ツール・制約・出力形式」の6ブロックを埋めれば、どのモデルでも安定する。出力形式には必ず具体例を1つ入れる。

---

## テンプレB: 素のSDK直叩き（線形パイプライン / 単純ReAct）— Python + Claude

依存を増やさず挙動を完全に把握したいとき。フレームワーク不要な案件はこれが最も保守しやすい。

`agent.py`:
```python
import os
import json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# 実際に使う最新モデルIDは claude-api スキル等で確認して差し替える
MODEL = "claude-sonnet-4-5"  # 例。案件時点の最新・適切なIDに置き換える

SYSTEM_PROMPT = """..."""  # テンプレAで作った文面を入れる

# --- ツール定義 ---
TOOLS = [
    {
        "name": "search_docs",
        "description": "社内文書を検索して関連する断片を返す",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "検索クエリ"}
            },
            "required": ["query"],
        },
    }
]

# --- ツールの実体 ---
def search_docs(query: str) -> str:
    # ここに実際の検索処理を書く（DB検索、API呼び出しなど）
    return "検索結果のダミー"

TOOL_IMPL = {"search_docs": search_docs}

def run_agent(user_input: str, max_turns: int = 10) -> str:
    messages = [{"role": "user", "content": user_input}]
    for _ in range(max_turns):  # ReActループの上限（暴走防止）
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            # ツールを呼ばず最終回答した
            return "".join(b.text for b in resp.content if b.type == "text")

        # ツール呼び出しを実行して結果を返す
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                result = TOOL_IMPL[block.name](**block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        messages.append({"role": "user", "content": tool_results})

    return "最大ターン数に達しました（要調査）"

if __name__ == "__main__":
    print(run_agent("テスト入力"))
```

`requirements.txt`:
```
anthropic
```

`.env`（コミットしない。`.gitignore`に追加）:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## テンプレC: LangGraph（複雑な分岐・状態遷移・Human-in-the-Loop）— Python

状態遷移を明示的に制御したいとき。ノードとエッジで処理を組む。**Human-in-the-Loopは `interrupt()`＋`Command(resume=...)`＋checkpointer** で実装する（この3点セットが必須。checkpointerが無いと割り込みで状態を保存できない）。

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver  # 本番は PostgresSaver / SqliteSaver

class State(TypedDict):
    messages: Annotated[list, add_messages]
    draft: str

def draft_node(state: State) -> dict:
    # LLMで下書きを作る（例: langchain-anthropic の ChatAnthropic を呼ぶ）
    return {"draft": "下書き内容..."}

def human_review_node(state: State) -> dict:
    # 実行をここで一時停止し、下書きを人間に提示して承認/修正を待つ。
    # interrupt() は初回呼び出しで GraphInterrupt を送出してグラフを止める。
    decision = interrupt({"draft": state["draft"], "question": "承認する? (approve/edit)"})
    # 再開後、Command(resume=...) で渡した値が decision に入る
    return {"messages": [("assistant", f"人間の判断: {decision}")], "draft": state["draft"]}

def route_after_review(state: State) -> str:
    # add_messages はタプルを Message オブジェクトに変換するので .content で読む
    last = state["messages"][-1].content if state["messages"] else ""
    return "execute" if "approve" in last else "draft"

def execute_node(state: State) -> dict:
    # 承認後の実行（外部送信など、取り返しのつかない操作はここ）
    return {"messages": [("assistant", "実行完了")]}

builder = StateGraph(State)
builder.add_node("draft", draft_node)
builder.add_node("human_review", human_review_node)
builder.add_node("execute", execute_node)
builder.add_edge(START, "draft")
builder.add_edge("draft", "human_review")
builder.add_conditional_edges("human_review", route_after_review,
                              {"execute": "execute", "draft": "draft"})
builder.add_edge("execute", END)

graph = builder.compile(checkpointer=InMemorySaver())  # interrupt には checkpointer 必須

# --- 実行と再開 ---
config = {"configurable": {"thread_id": "approval-123"}}  # 同一threadで中断/再開が繋がる
result = graph.invoke({"messages": []}, config=config)
if "__interrupt__" in result:                 # 割り込みが発生＝人間の入力待ち
    payload = result["__interrupt__"][0].value
    print("承認待ち:", payload)
    human_decision = "approve"                # 実際はUI/API経由で受け取る
    graph.invoke(Command(resume=human_decision), config=config)  # 同一configで再開
```
- `interrupt()` を含むノードは、再開時に**ノード先頭から再実行**される（副作用のある処理は `interrupt()` より後に置く）。
- `thread_id` を揃えて `Command(resume=...)` で再開する。中断中の状態は checkpointer が保持する。
- 本番は `InMemorySaver` を `PostgresSaver`/`SqliteSaver` に置き換える（プロセス再起動をまたいで再開できる）。

`requirements.txt`:
```
langgraph
langchain-anthropic   # 使うモデルのプロバイダに合わせる
```

> LangGraph のAPIはバージョンで変わる。`interrupt`/`Command`/checkpointer の現行仕様は公式ドキュメント（docs.langchain.com の LangGraph interrupts）で確認する。

---

## テンプレD: マルチエージェント（役割分担）— CrewAI例 / Python

役割特化のエージェントを素早く協調させたいとき。

```python
from crewai import Agent, Task, Crew, Process

researcher = Agent(
    role="リサーチャー",
    goal="与えられたテーマの正確な情報を集める",
    backstory="一次情報を重視し、裏取りを怠らない調査員",
    verbose=True,
)
writer = Agent(
    role="ライター",
    goal="リサーチ結果を分かりやすい記事にまとめる",
    backstory="専門用語を噛み砕いて書くのが得意な編集者",
    verbose=True,
)

research_task = Task(
    description="{topic} について信頼できる情報を収集する",
    expected_output="出典付きの箇条書きメモ",
    agent=researcher,
)
write_task = Task(
    description="収集したメモを1000字程度の記事にする",
    expected_output="見出し付きの記事本文",
    agent=writer,
    context=[research_task],  # リサーチ結果を受け取る
)

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    process=Process.sequential,
)
result = crew.kickoff(inputs={"topic": "入力テーマ"})
print(result)
```

> マルチエージェントは単一エージェントで足りないと確認してから採用する。コスト・デバッグ難度が上がる。

---

## テンプレE: MCPサーバー（ツールを標準化して複数エージェントで再利用）

ツールを複数のクライアント/エージェントで使い回したいとき。Python SDK例。

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-tools")

@mcp.tool()
def get_weather(city: str) -> str:
    """指定した都市の現在の天気を返す"""
    # 実際のAPI呼び出しをここに書く
    return f"{city} は晴れ"

@mcp.tool()
def create_ticket(title: str, body: str) -> str:
    """課題管理システムにチケットを作成し、URLを返す"""
    # 実際の作成処理
    return "https://tracker.example.com/TICKET-123"

if __name__ == "__main__":
    mcp.run()  # stdio または指定トランスポートで起動
```

`requirements.txt`:
```
mcp
```

Claude Code等のMCPクライアントの設定に、このサーバーの起動コマンドを登録すれば、ツールがエージェントから使えるようになる。

---

## テンプレF: ノーコード（n8n）でのフロー構築手順

コードを書かずにSaaS連携・トリガー駆動の自動化を作るとき。GUIなので手順で記述する。

1. **トリガーノードを置く**: 何で起動するか（Webhook受信 / 定期実行(Cron) / 特定SaaSのイベント）を選ぶ。
2. **入力の整形ノード**: 受け取ったデータを後続で使う形に整える（Set/Editノード）。
3. **LLMノード**: 使うモデルのノード（またはHTTP RequestノードでLLM APIを叩く）を置き、テンプレAのシステムプロンプトを設定する。
4. **分岐ノード（必要なら）**: LLMの出力に応じて処理を分ける（IF/Switchノード）。
5. **アクションノード**: 結果を書き込む先（Notion/Slack/DB/メール等）のノードを置く。
6. **エラーハンドリング**: 失敗時の通知フロー（Error Triggerノード）を別途つなぐ。
7. **テスト実行**: サンプル入力で1件流し、各ノードの出力を確認してから本番有効化する。

---

## テンプレG: Claude Codeのサブエージェント / スキルとして常駐させる

このメタエージェント自体、または作ったエージェントを、Claude Codeの拡張として使うとき。

サブエージェント `.claude/agents/agent-builder.md`:
```markdown
---
name: agent-builder
description: AIエージェントの要件を受け取り、ワークフロー分解・工数見積り・ツール選定・成果物生成まで一気通貫で行う
tools: Read, Write, Edit, Grep, Glob, WebSearch, WebFetch
---

（ここに 00-meta-agent-prompt.md のコピペ用プロンプト本体をそのまま貼る）
```

スキル `.claude/skills/agent-builder/SKILL.md` として登録する場合も、ボディに同じプロンプトを入れ、`description` に発動条件を書く。

---

## テンプレH: 評価テストケース（フェーズ5とセット）

成果物と必ずペアで作る。詳細は [`06-evaluation-and-iteration.md`](./06-evaluation-and-iteration.md)。

`evalset.jsonl`:
```jsonl
{"id": 1, "input": "入力例1", "expected": "期待する出力または合格条件", "must_include": ["必須要素A"], "must_not_include": ["禁止要素X"]}
{"id": 2, "input": "境界値の入力", "expected": "...", "must_include": [], "must_not_include": []}
{"id": 3, "input": "情報不足の入力（確認を返すべきケース）", "expected": "推測せず確認を返す", "must_include": ["確認"], "must_not_include": []}
```

評価スクリプトの骨子:
```python
import json

def evaluate(run_agent):
    passed, failed = 0, 0
    with open("evalset.jsonl", encoding="utf-8") as f:
        for line in f:
            case = json.loads(line)
            out = run_agent(case["input"])
            ok = all(w in out for w in case["must_include"]) and \
                 not any(w in out for w in case["must_not_include"])
            if ok:
                passed += 1
            else:
                failed += 1
                print(f"FAIL #{case['id']}: {out[:200]}")
    print(f"passed={passed} failed={failed}")
```

---

## テンプレI: OpenAI Agents SDK（マルチエージェント＋handoffs、Claudeも可）— Python

プロバイダ非依存の軽量マルチエージェント。役割別エージェントを **handoffs（委譲）** で繋ぐ。公開APIは `Agent` / `Runner` / `@function_tool` / `handoff` / `Guardrail` / `SQLiteSession` と小さい。**Claudeを使うなら LiteLLM 経由**（`pip install "openai-agents[litellm]"`）。

```python
from agents import Agent, Runner, function_tool
from agents.extensions.models.litellm_model import LitellmModel
import os

# Claude を LiteLLM 経由で使う（OpenAI以外のモデルはこの形）
claude = LitellmModel(model="anthropic/claude-sonnet-4-5",
                      api_key=os.environ["ANTHROPIC_API_KEY"])

# ツール = Python関数（スキーマは自動生成、Pydanticで検証）
@function_tool
def search_orders(user_id: str) -> str:
    """ユーザーの注文履歴を返す。"""
    return "注文A(発送済), 注文B(処理中)"

# 専門エージェント
refund_agent = Agent(
    name="Refund Agent",
    instructions="返金の可否を判断し、手順を案内する。",
    model=claude,
)
support_agent = Agent(
    name="Support Agent",
    instructions="一次対応。返金が絡む場合は Refund Agent に handoff する。",
    model=claude,
    tools=[search_orders],
    handoffs=[refund_agent],   # LLMには transfer_to_refund_agent ツールとして見える
)

result = Runner.run_sync(support_agent, "注文Bを返金したい。user_id=42")
print(result.final_output)   # どのエージェントが答えたか等のメタも result に入る
```
- `Runner` が実行・ツール呼び出し・handoffを回し、`RunResult`（最終出力＋メタ）を返す。
- 会話継続は `SQLiteSession`、安全側は `Guardrail`、外部ツールは MCP サーバーを drop-in で接続可。
- **プロバイダ非依存**: GPT系はネイティブ、Claude/Ollama等は LiteLLM 経由。モデル選定は [`04`](./04-tool-selection-matrix.md) の結論に合わせる。

`requirements.txt`:
```
openai-agents[litellm]
```
> APIは 0.2.x 系で流動的。`Agent`/`Runner`/handoff/LiteLLM の現行仕様は公式（openai.github.io/openai-agents-python）で確認する。

---

## テンプレJ: RAGパイプライン（pgvector）— Python

社内文書に根拠づけて答えるとき。既存PostgreSQLに `pgvector` を載せ、インフラを増やさない構成（[`04`](./04-tool-selection-matrix.md) カテゴリ4の推奨）。**取り込み（一度）** と **検索＋生成（都度）** の2段。

```sql
-- 一度だけ: 拡張とテーブル
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE docs (
  id bigserial PRIMARY KEY,
  content text NOT NULL,
  embedding vector(1024)          -- 使うEmbeddingモデルの次元に合わせる
);
CREATE INDEX ON docs USING hnsw (embedding vector_cosine_ops);  -- 近似最近傍
```

```python
# ingest.py — 取り込み: チャンク分割 → Embedding → 保存
import os, psycopg
from anthropic import Anthropic   # Embeddingは利用中の埋め込みAPIに置換

conn = psycopg.connect(os.environ["DATABASE_URL"])

def chunk(text: str, size: int = 800, overlap: int = 100):
    for i in range(0, len(text), size - overlap):
        yield text[i:i + size]

def embed(text: str) -> list[float]:
    # 実際のEmbeddingモデル呼び出しに置き換える（次元をテーブルと一致させる）
    ...

def ingest(doc_text: str):
    with conn.cursor() as cur:
        for c in chunk(doc_text):
            # リストを直接渡すとPostgreSQLの配列リテラルになり vector にキャストできない。
            # str(list) は '[0.1, 0.2, ...]' 形式で vector の入力形式と一致する。
            # （pgvector パッケージの register_vector を使う方法でも可）
            cur.execute("INSERT INTO docs (content, embedding) VALUES (%s, %s::vector)",
                        (c, str(embed(c))))
    conn.commit()
```

```python
# ask.py — 検索＋根拠つき生成
import os, psycopg, anthropic
from ingest import embed   # 同じEmbeddingモデルを使う（次元・正規化を揃える）

conn = psycopg.connect(os.environ["DATABASE_URL"])
client = anthropic.Anthropic()

def retrieve(query: str, k: int = 5) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM docs ORDER BY embedding <=> %s::vector LIMIT %s",
            (str(embed(query)), k))   # <=> はコサイン距離
        return [r[0] for r in cur.fetchall()]

def answer(query: str) -> str:
    context = "\n\n".join(retrieve(query))
    msg = client.messages.create(
        model="claude-sonnet-4-5", max_tokens=1024,
        system="以下のコンテキストのみを根拠に答える。無ければ「情報なし」と言う。推測しない。",
        messages=[{"role": "user", "content": f"<context>\n{context}\n</context>\n\n質問: {query}"}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")
```
- 精度が要れば ハイブリッド検索（全文＋ベクトル＋リランク）へ拡張（[`04`](./04-tool-selection-matrix.md)）。
- 「RAGが本当に要るか」を先に問う（[`10`](./10-claude-code-mcp-servers.md)/[`04`](./04-tool-selection-matrix.md)）。長文コンテキストに全部入るなら検索基盤を作らない。

`requirements.txt`:
```
anthropic
psycopg[binary]
```

---

## テンプレK: ガードレール（入出力フィルタ）— Python

機密・不適切入出力を防ぐ最小の砦。プロンプト頼みにせず、コードで検査する（安全設計は [`08 §6.5`](./08-agent-primitives-and-composition.md)・[`14 §6`](./14-prompt-and-context-engineering.md)）。

```python
import re

PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{4}-\d{4}\b"),          # 電話番号例
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),   # メール
]
BLOCKED_TOPICS = ["社外秘", "パスワード"]

def check_input(text: str) -> tuple[bool, str]:
    for p in PII_PATTERNS:
        if p.search(text):
            return False, "個人情報が含まれるため処理できません"
    return True, ""

def redact(text: str) -> str:                       # 外部送信前にマスキング
    for p in PII_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text

def check_output(text: str) -> tuple[bool, str]:
    for t in BLOCKED_TOPICS:
        if t in text:
            return False, f"禁止トピック({t})を含む出力をブロックしました"
    return True, ""

def guarded_run(agent_fn, user_input: str) -> str:
    ok, reason = check_input(user_input)
    if not ok:
        return reason
    out = agent_fn(redact(user_input))
    ok, reason = check_output(out)
    return out if ok else reason
```
- 取り返しのつかない操作の承認は Human-in-the-Loop（テンプレC）／Claude Codeなら[フック](./12-claude-code-hooks-and-plugins.md)の `PreToolUse` deny で確定的に。
- 過検出/検出漏れはテストセット（テンプレH）で継続調整する。

---

## テンプレL: ストリーミング付きエージェントループ — Python + Claude

ユーザーに逐次表示したいUI向け。テンプレBのループを `stream` 化する。

```python
import anthropic
client = anthropic.Anthropic()

def stream_answer(messages, tools, system):
    with client.messages.stream(
        model="claude-sonnet-4-5", max_tokens=1024,
        system=system, tools=tools, messages=messages,
    ) as stream:
        for text in stream.text_stream:   # 生成テキストを逐次受け取る
            print(text, end="", flush=True)
        final = stream.get_final_message()  # 完了後にtool_use等を含む最終メッセージ
    return final
```
- ツール使用を伴う場合は、`final.stop_reason == "tool_use"` を見てテンプレBと同じくツール実行→`tool_result`追加→再ストリーム、をループする。
- Agent SDK 側のストリーミングは [`11`](./11-claude-code-tool-use-and-sdk.md)（SDKの streaming 機能）。

---

## テンプレM: 可観測性（トレーシング）の配線

エージェントの実行を追跡・評価・回帰確認できるようにする（[`06`](./06-evaluation-and-iteration.md) と対）。

- **OpenTelemetry**: Agent SDK は OTel 出力に対応（[`11`](./11-claude-code-tool-use-and-sdk.md) 周辺機能）。既存の可観測性基盤（Grafana/Datadog等）に流す。
- **LLM特化プラットフォーム**（Langfuse / LangSmith / Braintrust / Arize Phoenix 等）: 実行トレース・スコア推移・A/Bを継続追跡（[`04`](./04-tool-selection-matrix.md) カテゴリ7）。
- 最小構成: 各エージェント実行の `入力 / 使ったツールと結果 / 出力 / トークン / レイテンシ / 成否` を1行の構造化ログ（JSON）で残すだけでも、後から回帰と異常を追える。

```python
import json, time, uuid

def traced(agent_fn, user_input: str) -> str:
    t0 = time.time(); trace_id = str(uuid.uuid4())
    try:
        out = agent_fn(user_input); status = "ok"
    except Exception as e:
        out = ""; status = f"error:{e}"
        raise
    finally:
        print(json.dumps({"trace_id": trace_id, "status": status,
                          "latency_ms": int((time.time()-t0)*1000),
                          "input_len": len(user_input), "output_len": len(out)},
                         ensure_ascii=False))
    return out
```

---

## テンプレN: デプロイ（Docker）＋ CI評価

「動く」を「動き続ける」にする最小構成（[`03`](./03-task-and-effort-breakdown.md) の運用系タスク）。

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 秘密情報はイメージに焼かず、実行時に環境変数で注入する
CMD ["python", "agent.py"]
```

CIで評価を自動実行（`.github/workflows/eval.yml`）:
```yaml
name: agent-eval
on: [push, pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: python run_eval.py   # テンプレHの評価を実行し、合格ライン未満なら非0で落とす
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```
- 秘密情報はイメージ・リポジトリに置かず、CIシークレット／実行時環境変数で注入する。
- プロンプト・モデル・ツールを変えるたびにCIで評価を回し、回帰を検知する（[`06`](./06-evaluation-and-iteration.md)）。
- 常時稼働・スケール・チャット統合などデプロイ方式の選定は [`04`](./04-tool-selection-matrix.md) カテゴリ9、エンタープライズなクラウド運用は [`15`](./15-bedrock-vertex-deployment.md)。

---

## テンプレO: Claude Code自体をCI・スクリプトで使う（headless `claude -p`）

テンプレNは「作ったエージェントの評価CI」。これは**Claude Code自体を自動化の部品にする**方（非対話モード）。エージェントを新しく実装せずに、`claude -p` 一発で「エージェント的な仕事」をパイプラインへ組み込める——**フェーズ3.5の再利用優先の観点で、自作の前にこれで足りないか検討する価値がある**。

### 基本形
```bash
# 単発実行（-p = 非対話）。CI/スクリプトでは --bare 推奨:
# フック・スキル・MCP・CLAUDE.md の自動探索をスキップし、どのマシンでも同じ結果にする
claude --bare -p "このファイルを要約して" --allowedTools "Read"

# パイプで流し込み、結果をリダイレクト（普通のCLIツールとして振る舞う）
cat build-error.txt | claude -p 'このビルドエラーの根本原因を簡潔に' > output.txt
```
- `--bare` では認証は `ANTHROPIC_API_KEY`（または `--settings` のapiKeyHelper、Bedrock/Vertexは各資格情報）。
- `--allowedTools` は権限ルール構文（[`16`](./16-claude-code-memory-and-permissions.md)）: `--allowedTools "Bash(git diff *),Read,Edit"`。
- ベースライン制御は `--permission-mode`（`dontAsk`=許可済み以外を自動拒否＝ロックダウンCI向け／`acceptEdits`=編集を自動承認）。

### 構造化出力（スクリプトで受ける）
```bash
# JSON（result / session_id / total_cost_usd 等のメタ込み）
claude -p "このプロジェクトを要約" --output-format json | jq -r '.result'

# スキーマ強制（structured_output に準拠JSONが入る）
claude -p "auth.py の主要関数名を抽出" --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}' \
  | jq '.structured_output'

# 会話の継続（同一ディレクトリで）
session_id=$(claude -p "レビュー開始" --output-format json | jq -r '.session_id')
claude -p "DBクエリ部分を深掘りして" --resume "$session_id"
```

### package.json に「Claudeリンター」を足す例
```json
{
  "scripts": {
    "lint:claude": "git diff main | claude -p \"you are a typo linter. for each typo in this diff, report filename:line on one line and the issue on the next. return nothing else.\""
  }
}
```

### GitHub Actions で PR レビュー
公式の GitHub Actions 統合（[github-actions](https://code.claude.com/docs/en/github-actions)、`@claude` メンション対応）を使うのが本筋。最小の自前ワークフローなら:
```yaml
name: claude-pr-review
on: [pull_request]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: npm install -g @anthropic-ai/claude-code
      - run: |
          git diff origin/${{ github.base_ref }} | claude --bare -p \
            --append-system-prompt "セキュリティエンジニアとして脆弱性を重点レビューする" \
            --output-format json > review.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - run: jq -r '.result' review.json
```
- diffを**パイプで渡す**とBash権限なしで読ませられる（権限を最小にできる）。
- 秘密情報はCIシークレットで注入。`--bare`でローカル設定の混入を防ぐ。
- スキルも `-p` で使える: プロンプト文字列に `/skill-name` を含めると展開される。

> `claude -p` のフラグ・出力仕様は更新される。[headless公式](https://code.claude.com/docs/en/headless)と `claude --help` で現行を確認する。
