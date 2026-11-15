# AI Agent Platform  デプロイ・運用手順書

## 1. 概要

本書は AI Agent Platform を **閉塞ネットワーク（NW）環境**へ持ち込み、安定稼働させるための手順をまとめたものです。  
インターネット接続環境での資材準備 → Docker イメージのビルドと保存 → 閉塞NWへの持ち込みと展開 → 日常運用の 4 フェーズで構成されます。

---

## 2. 前提・用語

| 用語 | 説明 |
|---|---|
| **インターネット接続環境** | pip/docker pull が可能な社外・検証端末 |
| **閉塞NW環境** | インターネット通信が遮断されたオンプレミスサーバー |
| **資材 USB / 媒体** | インターネット接続環境で作成したファイル群を閉塞NWへ持ち込む記録媒体 |

---

## 3. インターネット接続環境での資材準備

### 3.1 リポジトリのクローンと依存パッケージの確認

```bash
git clone <repository-url> ai-agent-platform
cd ai-agent-platform
pip install -r requirements.txt   # ローカルの動作確認用
pytest -q                          # 全テストが通ることを確認
```

### 3.2 Python wheel の収集

```bash
bash docker/download_offline_assets.sh
```

実行後、以下のディレクトリが生成されます。

```
docker/
  wheels/   ← requirements.txt の全 .whl ファイル
  cache/
    tiktoken/ ← トークナイザー辞書
```

### 3.3 Docker イメージのビルド

```bash
# リポジトリルートで実行
docker build -f docker/Dockerfile -t ai-agent-platform:latest .
docker build -t litellm:offline ghcr.io/berriai/litellm:main-latest  # 事前 pull 済み前提
```

### 3.4 Docker イメージの保存（.tar.gz 化）

```bash
mkdir -p dist

docker save ai-agent-platform:latest | gzip > dist/ai-agent-platform.tar.gz
docker save ghcr.io/berriai/litellm:main-latest | gzip > dist/litellm.tar.gz
```

### 3.5 資材一覧

```
dist/
  ai-agent-platform.tar.gz
  litellm.tar.gz
docker/
  docker-compose.yml
  litellm_config.yaml
  wheels/          (Python wheels)
  cache/           (tokenizer caches)
agents/            (エージェント定義ファイル)
.env.example
docs/
```

以上を USB または社内ファイル転送手順に従って閉塞NW環境へ持ち込みます。

---

## 4. 閉塞NW環境への持ち込みと初回展開

### 4.1 Docker イメージの読み込み

```bash
docker load < dist/ai-agent-platform.tar.gz
docker load < dist/litellm.tar.gz
```

### 4.2 環境変数ファイルの設定

```bash
cp .env.example .env
vi .env   # 実際のエンドポイントや API キーを設定
```

主な設定項目：

| 変数 | 説明 |
|---|---|
| `LITELLM_API_KEY` | LiteLLM が LLM バックエンドへ接続するキー（ローカルは "dummy" 可） |
| `DIFY_MCP_URL` | 本番 Dify MCP サーバー URL（検証時は `http://mock-dify-mcp:8001/mcp`） |
| `DB_PATH` | SQLite DB の保存先（ボリュームマウントパスに合わせる） |

### 4.3 サービス起動

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d
```

起動確認：

```bash
docker compose -f docker/docker-compose.yml ps
curl http://localhost:8000/v1/models
```

### 4.4 動作確認（疎通テスト）

```bash
# エージェント一覧取得
curl http://localhost:8000/v1/models

# knowledge_qa エージェントへの質問（非ストリーミング）
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"knowledge_qa","messages":[{"role":"user","content":"有給休暇の申請方法を教えてください"}]}'

# ストリーミングテスト
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"knowledge_qa","messages":[{"role":"user","content":"有給休暇の申請方法を教えてください"}],"stream":true}'
```

---

## 5. 日常運用

### 5.1 エージェント定義のホットリロード

`agents/` ディレクトリはコンテナにボリュームマウントされているため、  
`config.yaml` や `system_prompt.md` を編集するだけで次リクエストから反映されます。  
コンテナ再起動は不要です。

### 5.2 ログ確認

```bash
# リアルタイムログ
docker compose -f docker/docker-compose.yml logs -f ai-agent-platform

# 過去ログ（JSON 構造化ログ）
docker compose -f docker/docker-compose.yml logs ai-agent-platform | grep trace_id
```

### 5.3 バックアップ

```bash
# SQLite DB のバックアップ（data/ をホストにマウントしているため直接コピー可）
cp -r data/ backup/data_$(date +%Y%m%d)/

# agents/ 定義ファイルのバックアップ
cp -r agents/ backup/agents_$(date +%Y%m%d)/
```

### 5.4 TTL クリーンアップ（短期記憶・一時ファイルの自動削除）

短期記憶は `short_term_ttl_days`（デフォルト 30 日）を超えたレコードを  
次回アクセス時に自動削除します。  
手動で即時クリーンアップを行う場合は以下を実行します。

```bash
docker exec ai-agent-platform python - <<'PY'
from core.adapters.local_db import SQLiteMemoryStore
store = SQLiteMemoryStore()
# TTL パージは get_short_term() 呼び出し時に自動実行される
# 全ユーザーの期限切れレコードを強制パージする場合:
import sqlite3, os
from datetime import datetime, timedelta
conn = sqlite3.connect(os.environ.get("DB_PATH", "data/data.db"))
cutoff = datetime.utcnow() - timedelta(days=30)
conn.execute("DELETE FROM short_term_memories WHERE created_at < ?", (cutoff,))
conn.commit()
conn.close()
print("クリーンアップ完了")
PY
```

### 5.5 コンテナ更新手順（新バージョン適用）

1. インターネット接続環境で新バージョンのイメージをビルドし `dist/*.tar.gz` を更新  
2. 資材を閉塞NWへ持ち込み  
3. 閉塞NW環境で以下を実行

```bash
docker load < dist/ai-agent-platform.tar.gz
docker compose -f docker/docker-compose.yml up -d --no-build
```

---

## 6. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `GET /v1/models` が 500 | agents/ の config.yaml が壊れている | `docker logs ai-agent-platform` で Pydantic バリデーションエラーを確認し修正 |
| LLM が応答しない | vLLM / Ollama が起動していない | `docker compose ps` と LLM ホストのプロセスを確認 |
| `database is locked` | 複数プロセスが同一 DB に接続 | コンテナを 1 つだけ起動しているか確認；WAL モードへの変更を検討 |
| ストリーミングが途中で切れる | タイムアウト設定が短い | `litellm_config.yaml` の `request_timeout` と FastAPI の timeout を延長 |
