# フェーズ4: 成果物テンプレート集

「保存・実行すれば動く」レベルの雛形。案件で確定したツールに対応するものを選び、埋めて使う。

> **注意**: モデルID・SDKのバージョン・APIの細部は変わる。Claudeを使う場合、Claude Code環境なら `claude-api` スキルで最新のモデルID・料金・パラメータを必ず確認してから確定すること。このファイルの値はプレースホルダを含む雛形。

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

状態遷移を明示的に制御したいとき。ノードとエッジで処理を組む。

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
    approved: bool

def draft_node(state: State) -> dict:
    # LLMで下書きを作る処理
    return {"messages": [("assistant", "下書き内容")]}

def human_review_node(state: State) -> dict:
    # ここで割り込み、人間の承認を待つ（interruptを使う）
    return state

def execute_node(state: State) -> dict:
    # 承認後の実行処理（外部送信など）
    return {"messages": [("assistant", "実行完了")]}

def route_after_review(state: State) -> str:
    return "execute" if state.get("approved") else "draft"

graph = StateGraph(State)
graph.add_node("draft", draft_node)
graph.add_node("human_review", human_review_node)
graph.add_node("execute", execute_node)
graph.add_edge(START, "draft")
graph.add_edge("draft", "human_review")
graph.add_conditional_edges("human_review", route_after_review,
                            {"execute": "execute", "draft": "draft"})
graph.add_edge("execute", END)

app = graph.compile()  # 実運用では checkpointer を付けて状態を永続化する
```

`requirements.txt`:
```
langgraph
langchain-anthropic   # 使うモデルのプロバイダに合わせる
```

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
