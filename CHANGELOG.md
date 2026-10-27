# 変更履歴

## 0.3.0 — 2026-10-27

- TACACS SSH → 共通SSH → 共通Telnetの認証フォールバックを明確化。
- 各方式で特権EXEC `#` 到達まで確認し、TACACSで `>` の場合はenableせず共通SSHへフォールバック。
- 全方式失敗時に `<host>_NG.txt` を出力。
- 共通Telnetをユーザー名・パスワード認証へ対応。
- 資格情報をWindows DPAPIで暗号化保存する `setup-credentials.ps1` を追加。
- 復号した資格情報をプロセススコープの環境変数でTTLへ渡す `start-collector.ps1` を追加。
- 既存のTACACS失敗停止上限、事前確認、TFTP redirect、分割ログ等は維持。
- ワークフローテストを新しいフォールバック仕様へ更新。

Windows・Tera Term本体・Cisco実機・TFTPサーバーでの結合検証は未実施です。

## 0.2.1 — 2026-10-27

- 初回公開に向けて説明書とダイアログを汎用化。
- 実運用の入力・ログ・認証情報をコミットしないための除外設定を追加。
- Windows用ファイルの改行規則を明示。
- 既存のコマンド収集、事前確認、認証試行上限、方式別enable、TFTP未検証状態の処理を継続。

Windows・Tera Term本体・Cisco実機・TFTPサーバーでの結合検証は未実施です。
