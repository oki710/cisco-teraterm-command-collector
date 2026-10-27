# v0.2.1 検証結果

検証日：2026-10-27（日本時間）  
環境：Linux、Python 3.12.14、Oniguruma 6.9.9。  
**静的・限定モデル検証のみ。Windows、Tera Term本体、Cisco実機、TFTPサーバーでの実行は未実施です。**

## 実施結果

| 検証 | 結果 | 範囲・限界 |
| --- | --- | --- |
| TTL静的検査 | 指摘0件、1466行、最長419バイト、26ラベル、63種類の命令 | ネイティブの構文解析や型検査ではない |
| 正規表現 | 105ケース・インライン8件、失敗0 | 実Onigurumaによる評価。実際の受信ストリームなし |
| 入力・引用・試行上限 | 61ケース合格 | 実TTLソースの一部を実行する限定モデル |
| 方式別enable | 111ケース合格 | 37シナリオ×3保存方式。実認証なし |
| 出力パス | 8シナリオ群合格 | ホスト分離、同名化、予約名、日付またぎ、TFTP等 |
| 事前確認・報告・中止経路 | 14シナリオ群合格 | GUI・ファイルはメモリ内モデル。認証・転送処理は固定シナリオ |

collector.ttl SHA-256：`5846aaa20d5b742cfaad5c868ed99211b28bba890f93cddda21ccec79d5e3d5d`

## 再現手順

Pythonとlibonigを利用できる検証環境で、リポジトリのルートから実行します。同梱テストはマクロ利用時には不要です。

```bash
python3 tests/check_ttl.py collector.ttl
python3 tests/test_collector_regex.py collector.ttl
python3 tests/test_collector_procedures.py collector.ttl
python3 tests/test_privilege_policy.py collector.ttl
python3 tests/test_output_paths.py collector.ttl
python3 tests/test_workflow.py collector.ttl
```

libonigがない場合に別のエンジンで検証済みとはしません。モデルはTera TermのGUI、DDE、ネットワーク、WindowsファイルI/Oを再現しません。

## 配布前の確認

- 入力例・テストの接続先と認証値は架空のサンプルのみ。
- 実運用のホスト一覧、取得結果、コンフィグ、資格情報ファイルは配布しない。
- 会話・作業環境固有の記述を公開文書とダイアログから除外。
- `.gitignore` でローカル入力・取得ログ・秘密鍵等を除外。強制追加や追跡済みファイルには適用されない。
- TTLのUTF-8 BOM・CRLFを保持し、チェックサム対象は配布するソース・文書のみ。

## Windows・実機での受入項目（すべて未実施）

1. Windowsで起動し、日本語ダイアログ、取消、独立起動、専用INIを確認する。
2. 全保存方式の「事前確認のみ」で端末・接続・認証を開始せず、保存計画が入力と一致することを確認する。
3. 許可された1台でshow clockとshow versionを取得し、本文、日時、ファイル、11列の結果一覧を照合する。
4. TACACSの初期#／>、共通SSH・Telnetのenable、認証停止上限を試験環境で確認する。認証サーバーの正式なロック条件を先に確認する。
5. 未対応コマンド、認可拒否、切断、時間切れ、More、対話要求、ログ保存失敗時の結果と後続停止を確認する。
6. 2ホスト×2コマンド、統合モード、再実行、日付またぎ、長いパスの動作を確認する。
7. TFTP受信側フォルダを準備し、受信ファイルの存在・サイズ・本文を確認する。CLI完了だけで成功と断定しない。
8. 終了処理と要確認ホスト一覧、強制終了時の残存端末・部分ログを確認する。

実機結果には機種、OS版、Tera Term版、保存方式、観測結果を残し、認証値や実運用コンフィグを公開しないでください。
