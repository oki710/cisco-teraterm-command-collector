# Cisco IOS／IOS XE コマンド取得マクロ

**v0.1.1 — 利用環境の回答を反映。TACACSは初期特権EXEC、共通SSH・Telnetは必要時にenableを実行します。Windows上のTera Term・実機での動作は未検証です。**

複数ホストに順番に接続し、複数の `show` コマンドを実行します。起動時に保存方式と認証情報を選びます。対象機器の設定を保存・変更する処理はありません。セッション内の `terminal` 設定、共通SSH・Telnetで必要な場合の `enable`、TFTPモードの `redirect` を実行します。

## 最初に使う手順

1. ZIPを短いパスへ展開します。例：`C:\CiscoCollector`。ZIPの中から直接起動しないでください。
2. `hosts.example.txt` をコピーして `hosts.txt` とし、対象を **まず1台** だけ記入します。
3. `commands.example.txt` をコピーして `commands.txt` とし、最初は `show clock` と `show version` の2個にします。
4. `start-collector.cmd` を起動します。Tera Termが見つからない場合、同ファイル先頭の `TT_MACRO` に `ttpmacro.exe` の絶対パスを設定します。
5. ホスト一覧、コマンド一覧、保存方式、制限時間、TACACS失敗停止上限（1～3回）、保存先を選びます。
6. 使用する認証情報と、共通SSH・Telnetのenableパスワードを入力します。両方式のenableパスワードが同じ場合は、その選択もできます。認証情報をソースやテキストへ書く必要はありません。
7. 開始確認で件数を確認し、実行します。終了後、`summary.tsv` と取得本文を確認します。

`ttpmacro.exe "C:\CiscoCollector\collector.ttl"` のような独立起動も可能です。**接続済みのTera Termの「コントロール→マクロ」からは起動しません。** 既存の作業セッションに触れないよう、リンク済みの場合は開始前に停止します。

## 入力ファイル

### hosts.txt

```text
sw01.example.net
sw02.example.net
192.0.2.10
```

- 1行1ホスト。DNSホスト名またはIPv4アドレスを指定します。接続元PCで名前解決できる必要があります。
- 空行と、先頭が `#` または `;` のコメントを読み飛ばします。行末コメントは使用しません。
- UTF-8（BOMあり／なし）またはASCII、CRLF／LFに対応する処理です。UTF-16は使用しません。
- 大文字小文字だけが異なる重複名を含め、同じホスト表記の重複は接続前にエラーにします。ホスト名とIPなど別表記が同じ機器を指すことまでは判定しません。
- 上限1000件。SSHはTCP/22、TelnetはTCP/23。IPv6、ホストごとの別ポート、踏み台はこの版の対象外です。

### commands.txt

```text
show clock
show version
show ip interface brief
show interfaces status
```

- `show` を省略せず記載します。先頭・末尾の空白は除去します。
- 1行240バイト以内、最大256件。空行・コメントの規則はホスト一覧と同じです。
- コマンド実行中にヘルプ表示へ移る `?`、制御文字、入力ファイル側の `| redirect`／`| append`／`| tee`（省略形を含む）は拒否します。転送用のredirectはマクロが付加します。
- 通常の `| include`／`| exclude`／`| begin` などは使用できます。TFTPモードでさらにredirectを付加する構文は、対象の版で対応確認が必要です。
- `show interfaces status`／`show vlan brief` などは機種依存です。サンプルのスイッチ専用項目はコメントにしてあります。
- この版は取得用のshowが対象です。`ping`、`traceroute`、`dir`、設定変更、対話型コマンドを同じ一覧へ入れないでください。

## 保存方式

| 起動時の選択 | 保存先・構成 |
| --- | --- |
| ローカル統合／ホストごと | ホストごとに全コマンドを1ファイルへ保存 |
| ローカル統合／全ホスト | 全ホスト・全コマンドを `all_hosts.txt` へ保存 |
| ローカル分割 | ホスト×コマンドごとに別ファイルへ保存 |
| TFTP redirect | 機器からTFTPサーバーへコマンドごとに送信。PC側には転送操作のログと一覧を保存 |

毎回、選択した保存先の下に `cisco_YYYYMMDD_HHMMSS_乱数` フォルダを新規作成します。同名フォルダがある場合は再利用せず停止します。日時は実行PCのローカル時刻です。

共通で `summary.tsv`、`hosts_used.txt`、`commands_used.txt` を保存します。パスワードとユーザー名は書き込みません。ホスト／コマンドの番号は、コメントを除いた各一覧の上からの順番です。

出力例：

| モード | ファイル例 |
| --- | --- |
| ホスト統合 | `h0001_sw01.example.net__all.txt` |
| コマンド別 | `h0001_sw01.example.net__c001_show_clock.txt` |
| TFTP操作ログ | `h0001_sw01.example.net__tftp_receipts.txt` |

ログにはホスト・方式・コマンド番号・時刻・終了状態の区切りを入れます。コマンドのechoとプロンプトも含むテキストログです。コンソールからの取得なので、バイナリ一致や任意の改行幅を保証するファイル転送ではありません。

## 認証の順序

1. TACACS用のユーザー名・パスワードでSSH2接続。
2. 失敗した場合、共通SSHのユーザー名・パスワードでSSH2接続。
3. 失敗した場合、共通VTYパスワードでTelnet接続。

各方式1ホストにつき1回です。ユーザー名が空欄のSSH方式と、パスワードが空欄のTelnetはスキップします。ユーザー名を入力したSSH方式のパスワードを空欄／キャンセルにした場合は、取得全体を中止します。同じユーザー名（大文字小文字を区別しない）・同じパスワードのSSH情報が両欄へ入力された場合、共通SSH側の重複試行を省きます。同じユーザー名に異なるパスワードを指定した場合は、同一アカウントへの二重試行を避けるため接続前に停止します。共通SSHは別ユーザー名にするか、片方の方式を空欄で無効にしてください。AAA側の別名・realm等が同じアカウントを指すかどうかは検出しません。

ここでいう「TACACS用」「共通SSH」は**試す資格情報の区別**です。機器側のAAA認証をTACACS／ローカルへ強制切り替えする機能ではありません。共通SSHアカウントが利用できるかは、既存の機器設定に従います。

Telnetは `Password:` のみを要求するVTY認証を想定しています。`Username:` を要求された場合は `TELNET_USERNAME_REQUIRED` として取得しません。パスワードをユーザー名欄へ送信することはありません。

### TACACS失敗停止上限

既定値は **3回／取得セッション全体**、起動時の設定範囲は **1～3回** です。「5回でロックかもしれない」との回答を未確認条件として扱い、0（無制限）と4回以上の設定を廃止しました。

この値はパスワード誤りだけを数えるものではありません。**TACACS用SSHの試行でEXECプロンプトへ到達しなかった回数**です。TACACSを使わない機器、接続不能、認証時間超過も含みます。共通SSHで後から成功しても、この通算回数は減りません。

上限へ達したホストでは、残りの共通SSH／Telnetを試し、そのホストの取得まで行います。その次のホストへ進む前に停止します。上限に達したのが最後のホストなら、全件処理後に通常の結果を表示します。

**3回はロックアウトしないことを保証する値ではありません。** 実行前の失敗回数、他端末・別処理の試行、サーバー側のカウント期間は分かりません。カウンターは今回のマクロ起動内だけで、再起動すると0から始まります。上限で止まったら、資格情報と正式なロック条件を確認せず同じ一覧を繰り返し実行しないでください。共通SSHやenableの認証先も機器側AAA設定に従うため、この上限がサーバー側の全失敗を計測しているわけではありません。

### 方式ごとのenable処理

Tera Term 5.x、TACACSのSSH password認証、TACACSは初期 `#`、共通SSH・Telnetはenableが必要という回答を反映しています。enableを使うかどうかの一括選択は廃止しました。

| ログイン方式 | 初期プロンプト | 動作 |
| --- | --- | --- |
| TACACS用SSH | `#` | enableを送らず、取得の準備へ進む |
| TACACS用SSH | `>` | `TACACS_NOT_PRIVILEGED` を記録し、そのホストを中止 |
| 共通SSH | `>` | `enable` を1回送る。要求された場合だけ共通SSH用enableパスワードを1回送る |
| Telnet | `>` | `enable` を1回送る。要求された場合だけTelnet用enableパスワードを1回送る |
| 共通SSH・Telnet | `#` | 既に特権EXECなので、そのまま取得の準備へ進む |

- 共通SSHとTelnetのenableパスワードは別々に入力できます。両方式を有効にした場合、Telnet側で「共通SSH用と同じ」も選べます。既定の選択は別入力です。
- SSHログイン用、TelnetのVTY用のパスワードをenableへ自動流用しません。両方式とも無効ならenableパスワードを尋ねません。
- enableパスワードが空欄／入力取消の場合、パスワードなしでenableできる機器だけ続行します。`Password:` を要求する機器では、パスワードを送らず `ENABLE_PASSWORD_REQUIRED` としてそのホストを中止します。
- enable後は、元のホストの `>` を `#` に変えたプロンプトとの一致を確認します。別のホスト名、設定モード、再度のパスワード要求、拒否、時間切れでは取得しません。
- TACACSの初期 `>` は認証成功後の権限不足として扱い、TACACS失敗停止カウンターへ加算しません。enableを送ったり、共通方式で再ログインしたりしません。
- enableやコマンド認可で失敗しても、別アカウントへ再ログインしません。全保存方式で、特権EXECを確認してから取得します。

## 共有端末でのパスワードの扱い

- `passwordbox` で入力し、`getpassword`／`setpassword` や資格情報ファイルは使いません。
- まず秘密情報なしで専用Tera Termを起動し、リンク済み・未接続を確認してから認証用の接続要求を渡します。通常経路でパスワードを新規プロセスの起動引数へ残さない、公式に示された方法です。[1]
- 専用INIで自動ログ、履歴記録、TTSSHログ、ttyrec自動録画、ローカルエコー、セッション複製、パスワード再利用用保持を無効にします。[2]
- 認証とenableの入力中はログを開きません。ログ開始時の画面バッファ取り込みも無効です。[3]
- 通常終了、入力キャンセル、マクロが処理できる異常経路では、認証用変数を空にし、専用Tera Termへ切断・終了を指示します。

**実行中はマクロ用のTera Termを手で閉じたり、手動コマンドを入力したりしないでください。** リンク確認と接続要求は単一の原子的処理ではなく、その間にウィンドウを閉じる競合まで純TTLでは排除できません。

空文字代入は、OSのページファイル、クラッシュダンプ、メモリ上の過去コピーまでを安全消去する保証ではありません。強制終了・TTL実行時エラー・Tera Term異常終了では終了処理が動かない場合があります。ウィンドウが残ったときは、マクロと今回用の `Cisco Collector ...` ウィンドウを閉じてください。

入力したパスワードの非保存と、取得結果に秘密情報が含まれないことは別です。例えば `show running-config` の本文には機器の認証設定が含まれ得ます。出力先は業務上認められたアクセス制限のある場所を指定します。

## Tera Term自身のダイアログ

**純TTLによる完全無人の認証フォールバックは、この版の保証範囲外です。** TTSSHの認証失敗、通信エラー、初回ホスト鍵確認などで、Tera Term自身のダイアログ操作が必要になる場合があります。[4]

- 通常の認証拒否エラーは、内容を確認して `OK` で閉じると、マクロが次の方式へ進める場合があります。
- SSHホスト鍵の警告を自動受諾する設定は使用しません。初回の鍵は正しいフィンガープリントを確認します。ホスト鍵が変わった／確認できない場合は、**次方式へ進めずマクロ全体を中止**してください。
- 純TTLは認証拒否とホスト鍵警告の取消を確実には区別できません。鍵警告で中止する場合は、マクロの `End` で停止してから専用端末を閉じます。
- 切断要求後も接続中表示が続く場合は、全体を停止して専用ウィンドウの手動終了を案内します。`closett` 後のリンク切断だけをプロセス終了の証明とは扱いません。[5]

`/TIMEOUT` はTCP接続の制限であり、GUIダイアログ待ち全体を打ち切る保証ではありません。[6]

## TFTPモードの前提

送信するCLIの例：

```text
show version | redirect tftp://192.0.2.20/20261021_090000_123456_h0001_sw01_c002_show_version.txt
```

- 通信元は**取得PCではなくCisco機器**です。機器からサーバーへの到達性、TFTPの書込許可、ACL、既存のVRF／送信元設定を事前に確認します。
- サーバー側のフォルダ構成や新規ファイル作成許可は変更しません。この版はTFTPルートへのファイル名を生成します。
- 機器の `ip tftp source-interface` やルーティング、VRFを変更する処理はありません。
- `append` は対応URLに制約があるため使わず、コマンドごとの名前で `redirect` します。`redirect` は既存名を上書きし得ます。時刻・乱数・ホスト番号・コマンド番号で衝突を避ける構成ですが、受信側の既存名チェックまでは行いません。[7]
- `redirect` 自体の対応と、フィルタを含めた構文は機種・版で確認します。
- 生成するコマンド全体は400バイト以内です。超過時は送信せず `TFTP_COMMAND_TOO_LONG` と記録します。
- `TFTP_CLI_DONE_UNVERIFIED` は、転送操作後にプロンプトへ戻ったことだけを表します。**受信ファイルの存在・サイズ・本文はサーバー側で確認してください。**

TelnetとTFTPには通信内容の暗号化がありません。今回指定された既存の運用範囲で使用する前提です。

## 完了・失敗の見方

`summary.tsv` の列は `time / host / auth / phase / command_no / status / artifact` です。テキストエディターでも開けます。`phase=RUN` の開始・終了行で、全体の完了／中止を確認できます。開始行しかなければ、正常な終了処理まで到達していません。

| 状態 | 意味・次の確認 |
| --- | --- |
| `EXEC_PROMPT_REACHED` | ログイン後のEXECプロンプトを検出。コマンド権限の保証ではない |
| `LOCAL_CLI_DONE` | echoを確認し、既知のエラーを検出せず学習したプロンプトへ戻った |
| `TFTP_CLI_DONE_UNVERIFIED` | TFTP操作のCLIが終了。受信側で確認が必要 |
| `CLI_ERROR_TEXT_REVIEW` | CLIエラーに該当する文字列を検出。本文を確認する |
| `SSH_NOT_CONNECTED`／`SSH_EXEC_TIMEOUT` | SSH接続またはEXEC到達を確認できなかった。必ずしもパスワード誤りではない |
| `TELNET_USERNAME_REQUIRED` | ユーザー名ありのTelnetで、この版の認証方式とは異なる |
| `TACACS_NOT_PRIVILEGED` | TACACSでログインしたが初期 `>`。enable・別方式への再ログインをせず、そのホストを中止 |
| `ENABLE_*`／`UNEXPECTED_ENABLE_PROMPT` | enable要求・失敗・特権未到達・プロンプト相違。ログイン失敗とは別 |
| `ECHO_NOT_CONFIRMED_TIMEOUT` | 通常のコマンドechoを確認できない。端末表示やAAA、通信を確認 |
| `COMMAND_TIMEOUT`／`DISCONNECTED_INCOMPLETE` | 部分ログを保持し、その接続へ後続コマンドを送らない |
| `PAGING_DETECTED_INCOMPLETE` | ページングを検出。部分取得としてそのホストを中止 |
| `INTERACTIVE_PROMPT_ABORTED` | 対話入力が必要。自動応答せずそのホストを中止 |
| `PROMPT_CHANGED_ABORTED` | 学習したものと異なるプロンプトを検出。そのホストを中止 |
| `SKIPPED_SESSION_UNSAFE` | 直前の異常のため、そのホストの残コマンドを送信していない |
| `LOG_OPEN_FAILED` | ログを開けず、全体を中止 |

`LOCAL_CLI_DONE` は、任意のshow本文が意味的に正常であることや、全エラーメッセージを網羅していることまでは保証しません。`show logging` や大きな診断出力に過去のCLIエラーが含まれる場合、要確認として扱うことがあります。本文に実プロンプトと完全に同じ行が現れる場合も、端末マクロの完了判定には限界があります。

端末準備は `terminal no monitor` → `terminal length 0` → `terminal width 0` の順です。`terminal length 0` が失敗したホストは中止します。ほかの2つはプロンプトが戻るCLIエラーであれば記録して続けます。ページング抑制と幅0はCisco自身の自動操作資料でも使われています。[8]

終了コードは、0＝ローカル取得の処理完了、1＝取得失敗／中止、2＝入力や準備の不備、3＝失敗はないがTFTP受信未検証です。取消は1です。TFTP未検証と取得失敗が両方ある場合は1を優先します。すべてのコマンドの正しさは一覧・本文と合わせて判断してください。

## 制限時間・停止・復旧

- TCP接続：15秒。EXEC到達／認証プロンプト：30秒。
- 端末準備：各20秒。取得コマンド：起動時指定、既定120秒、5～7200秒。
- コマンドの制限時間はecho待ちからプロンプト復帰までの総時間です。途中でエラー文字列を検出しても無制限には延長しません。
- 時計計算は実行PCのローカル時計を使用し、日付またぎを処理します。実行中の手動時計変更や大きな時刻補正は制限時間に影響します。
- ホストは直列処理です。接続不能な1台の後は、停止上限等に達しない限り次のホストへ進みます。
- 手動で止める場合はマクロウィンドウの `End` で終了し、今回の専用Tera Termを閉じます。強制終了時は通常のcleanup完了を前提にしません。
- 再実行は新しいフォルダへ保存します。機器側のterminal設定は接続単位なので切断で終了します。TFTP側に送られたファイルとローカルの部分ログは残します。自動削除はしません。

## 確認済みの条件と残る確認

確認済み：Tera Term 5.x、TACACSはSSH password認証かつ初期特権EXEC、共通SSH・Telnetはenableが必要。

残る確認は、**TACACSの正式なロック条件（失敗回数、カウント期間、解除条件）**です。「5回」は現時点で未確定と扱っています。enableパスワードの方式間の共通性は起動時に選べるため、事前回答がなくても設定できます。方式ごとに1つのenableパスワードを使用する構成なので、同じ方式の機器間でも異なる場合は、対象を別のホスト一覧へ分けて実行するか設計調整が必要です。

実機受入では、TFTPを使う機器のredirect対応と、機器からサーバーへの到達・書き込み可否も確認します。パスワードの実値をチャットへ送る必要はありません。

## 同梱物

- `collector.ttl`：本体
- `collector.ini`：資格情報を含まない専用端末設定
- `start-collector.cmd`：起動ランチャー
- `hosts.example.txt`／`commands.example.txt`：編集用サンプル
- `PROMPT.txt`：改善済みの実装依頼
- `TEST_REPORT.md`：実施した検証と、Windows・実機での受入確認
- `tests/`：再現用のオフライン検証コード。マクロ実行には不要

## 参照した公式資料

1. [TTSSH command line — Notes on Specifying a Password](https://teratermproject.github.io/manual/5/en/commandline/ttssh.html)
2. [All items of Tera Term setup file](https://teratermproject.github.io/manual/5/en/setup/teraterm-ini.html)
3. [Tera Term MACRO — logopen](https://teratermproject.github.io/manual/5/en/macro/command/logopen.html)
4. [TTSSH setup — Suppressing message box](https://teratermproject.github.io/manual/5/en/setup/teraterm-ssh.html)、[TTSSH公式ソース](https://github.com/TeraTermProject/teraterm/tree/main/ttssh2/ttxssh)
5. [disconnect](https://teratermproject.github.io/manual/5/en/macro/command/disconnect.html)、[closett](https://teratermproject.github.io/manual/5/en/macro/command/closett.html)
6. [Tera Term command line](https://teratermproject.github.io/manual/5/en/commandline/teraterm.html)
7. [Cisco IOS XE — show Command Output Redirection](https://www.cisco.com/c/en/us/td/docs/routers/ios-xe/system-management/system-management/m_cf-shw-cmd-out-redirect-0.html)
8. [Cisco RADKit — Terminal & SFTP/SCP](https://radkit.cisco.com/docs/features/feature_terminal.html)
9. [TTL for / next](https://teratermproject.github.io/manual/5/en/macro/command/fornext.html)、[waitregex](https://teratermproject.github.io/manual/5/en/macro/command/waitregex.html)、[setsync](https://teratermproject.github.io/manual/5/en/macro/command/setsync.html)

仕様確認日：2026-10-21。将来のTera Term更新や機器OS差異をまたいだ動作保証ではありません。