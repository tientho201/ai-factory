# AI Factory

Dây chuyền phân cấp agent cho Claude Code. Bạn nêu ý tưởng, hệ thống chọn quy trình nặng nhẹ tùy việc, chạy những gì an toàn, và dừng lại hỏi bạn đúng chỗ đáng hỏi.

## Hai phần, đừng lẫn

**Phần dùng chung — đây là thứ bạn push lên GitHub.** Một repo duy nhất, dùng cho mọi dự án về sau:

```
ai-factory/
├── .claude-plugin/    manifest
├── skills/            7 skill
├── agents/            4 agent
├── hooks/             hàng rào chặn cứng
├── scripts/           công cụ
├── profiles/          hai bộ cấu hình mẫu
└── README.md
```

**Phần riêng từng dự án — không bao giờ push vào repo trên.** `.flow/` sinh ra trong mỗi dự án khi bạn chạy `init`: cấu hình riêng, trạng thái chạy, nhật ký, hàng đợi duyệt.

Repo plugin **không được chứa `.flow/`**. Nếu có, script sẽ tìm nhầm sang cấu hình của chính plugin thay vì của dự án bạn đang làm.

## Đưa lên GitHub

```bash
cd ai-factory
git init && git add -A
git commit -m "AI Factory"
git remote add origin git@github.com:TEN-BAN/ai-factory.git
git push -u origin main
```

Repo để public hay private đều được. Private thì máy nào cài cũng phải có quyền đọc repo đó.

## Dùng ở một dự án bất kỳ

Cài một lần cho máy:

```
/plugin marketplace add TEN-BAN/ai-factory
/plugin install ai-factory@ai-factory
```

Rồi ở **mỗi dự án**, chạy một lần duy nhất:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow.py" init
```

Lệnh này tạo `.flow/` trong dự án, chọn cấu hình mặc định, thêm đúng dòng cần thiết vào `.gitignore`, và tạo cầu nối `.flow/flow` để từ đó mọi lệnh đều ngắn gọn:

```bash
.flow/flow status
.flow/flow dashboard
```

Thực tế bạn không cần gõ lệnh init — Claude tự chạy khi thấy dự án chưa khởi tạo.

Sửa plugin thì push lên, các máy khác chạy `/plugin marketplace update` là có bản mới. Không phải đụng vào từng dự án.

Thử tại chỗ trước khi push: `/plugin marketplace add /duong/dan/ai-factory`

Xác minh chạy được: `bash scripts/selftest.sh` — 52 điểm kiểm tra, dựng repo giả trong thư mục tạm, không đụng repo thật.

## Commit gì trong dự án của bạn

`.flow/config.json` nên commit — đó là luật chung của cả nhóm cho dự án đó.

`.flow/runs/`, `.flow/queue/`, `.flow/current.json`, `.flow/flow` thì không. `init` đã thêm sẵn vào `.gitignore`.

## Lớp skill

`flow` là cửa vào duy nhất Claude tự nạp. Nó không chứa quy trình, chỉ đọc tình hình rồi gọi xuống:

| Skill | Nạp khi | Làm gì |
|---|---|---|
| `flow` | bạn nêu việc muốn làm | đọc hàng đợi, chọn tuyến, điều phối |
| `flow-route` | đầu mỗi việc | quyết định chạy mấy bước |
| `flow-tier` | cần biết có phải hỏi người không | luật phân cấp rủi ro |
| `flow-protocol` | cần đọc/ghi file nào | hợp đồng bàn giao |
| `flow-session` | trước task lớn | có nên cắt phiên mới |
| `flow-report` | sau mỗi task | viết báo cáo cho bạn đọc |
| `flow-resume` | nối tiếp việc cũ | lấy lại ngữ cảnh |

Muốn hệ thống giỏi thêm thì **viết thêm skill, đừng viết thêm agent**. Bốn agent (`flow-explorer`, `flow-planner`, `flow-coder`, `flow-verifier`) cố định, vì hạn chế công cụ của chúng là cơ chế thực thi chứ không phải lời mô tả. Verifier không sửa được code không phải vì được dặn, mà vì nó không có quyền Write.

## Bốn tuyến

Không phải việc nào cũng cần cả dây chuyền. Sửa một lỗi chính tả mà chạy bốn agent là đốt tiền.

| Tuyến | Khi nào | Chạy gì |
|---|---|---|
| Khảo sát | bạn hỏi để hiểu | explorer, dừng |
| Nhanh | 1 file, Tier 0 | coder → cổng máy |
| Gọn | 2-5 file, Tier ≤1, vùng đã biết | planner → coder → verifier |
| Đủ | Tier 2, vùng lạ, hoặc >5 file | cả bốn |

Tuyến được chọn bằng **bốn con số quan sát được**: tier, số file, vùng đã khảo sát chưa, repo có test không. Không chọn bằng cảm giác "việc này đơn giản" — vì model bỏ qua kiểm tra đúng vào lúc nó tự tin nhất, mà đó cũng là lúc nguy hiểm nhất.

Hai luật đè lên mọi tuyến: **Tier 2 luôn phải qua verifier**, và **có test thì luôn chạy cổng máy**.

## Hai bộ cấu hình

```bash
.flow/flow profile production   # mặc định
.flow/flow profile greenfield
```

`production` — tự động tắt, Tier 2 rộng: migration, auth, thanh toán, dependency, hạ tầng đều phải hỏi bạn.

`greenfield` — tự động bật tới Tier 2. Chỉ chặn thứ chạm **ra ngoài** repo: git push, deploy, publish, secret. Migration với dependency tự chạy.

## Bấm duyệt trên web

**Claude Code không lắng nghe ở đâu cả.** Không có cổng nào để trang web đẩy tin nhắn vào phiên đang chạy. Nên trang không gọi thẳng vào Claude — nó ghi quyết định ra file, Claude đọc file đó.

```bash
.flow/flow dashboard
```

Ba chế độ, gạt ngay trên trang:

**Hàng đợi** (mặc định) — bấm xong, quyết định vào `.flow/queue/`. Bạn quay lại chat gõ "tiếp", việc đầu tiên `flow` làm là `flow.py inbox` đọc hàng đợi rồi chạy tiếp. Trong lúc chờ không tốn gì.

**Agent thấy ngay** — dành cho lúc agent đang chạy `flow.py wait`. Bấm là nó thấy trong vài giây. Đổi lại nó đốt token quay vòng trong lúc chờ.

**Tự khởi động** — server chạy `claude -p` một phiên mới ngay khi bạn bấm. Bạn không phải gõ gì. Phải bật riêng vì nó tự động khởi động Claude:

```bash
.flow/flow dashboard --allow-spawn
```

Chế độ này ghép luôn với việc cắt phiên: mỗi lần duyệt là một phiên sạch.

## Trang có gì

Dải cam trên cùng chỉ hiện khi có việc chờ bạn — liếc một giây là biết. Còn lại thì nó là một dòng trạng thái im lặng.

Bảng task với viền trái dày mỏng theo tier: mảnh xám là tự chạy, xanh là mặc định, dày cam là phải duyệt. Bấm vào một task mở ra báo cáo của verifier, ghi chú của coder, kết quả từng cổng test, và ô để bạn gõ nhận xét.

Sơ đồ task nào chặn task nào. Nhật ký agent nào làm gì lúc nào, mất bao lâu. Token đã dùng kèm ước tính chi phí, và lời nhắc khi phiên dài quá thì nên cắt.

Nhận xét bạn gõ vào `tasks/<id>/feedback.md`. Agent bắt buộc đọc file này trước khi sửa lại một task bị trả về — bạn biết thứ mà cả nó lẫn verifier đều không biết.

## Cắt phiên để tiết kiệm token

Mỗi lượt trong một phiên phải gửi lại toàn bộ lịch sử. Phiên chạy đến task thứ sáu đang cõng cả năm task trước dù chẳng liên quan.

```bash
.flow/flow hand-off T3
```

Ghi `handoff.md` — một trang chứa mọi thứ phiên sau cần: đang đến đâu, task kế tiếp, đọc file nào, đã chốt gì. Rồi bạn `/clear` và nhắn "tiếp tục T4".

**Cái bẫy:** phiên mới cũng phải nạp lại đống file đó, và vứt luôn prompt cache đang ấm. Với task nhỏ, cắt phiên **đắt hơn** là chạy tiếp. `flow-session` có ngưỡng cụ thể; trang web hiện số token để bạn tự thấy.

## Lệnh hay dùng

```bash
.flow/flow inbox              # đọc hàng đợi — Claude tự chạy đầu mỗi lượt
.flow/flow status             # tiến độ
.flow/flow runs               # các run đã có
.flow/flow resume <RUN>       # mở lại việc dở
.flow/flow usage              # token và chi phí
.flow/flow note T3 "..."      # ghi nhận xét
.flow/flow dashboard               # bảng điều khiển
bash scripts/selftest.sh                  # tự kiểm tra 52 điểm
```

## Thông báo

Tạo `.env.flow`: `FLOW_SMTP_USER`, `FLOW_SMTP_PASS` (App Password 16 ký tự, lấy ở myaccount.google.com → Security → 2-Step Verification → App passwords), `FLOW_NOTIFY_TO`. Thử bằng `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/notify.py" --test`.

Nếu bạn đã kết nối Gmail connector trong Claude Code thì không cần bước này — bảo Claude dùng connector đó để gửi, sạch hơn và không phải quản App Password.

Telegram: `FLOW_TELEGRAM_TOKEN` + `FLOW_TELEGRAM_CHAT_ID`. Slack/Discord: `FLOW_WEBHOOK_URL`.

## Giới hạn nên biết

**Chi phí.** Tuyến Đủ tốn gấp nhiều lần một agent đơn. Đó là lý do có bộ chọn tuyến — nhưng nếu bạn toàn làm việc nhỏ thì hệ thống này không đáng.

**Chạy song song.** Chỉ an toàn khi các task không trùng file. `plan-import` cảnh báo khi phát hiện trùng; đừng bỏ qua. Nghi ngờ thì chạy tuần tự — sửa conflict tốn hơn là chờ.

**Dashboard không có đăng nhập.** Chỉ nghe trên 127.0.0.1. Duyệt từ điện thoại thì mở tunnel (`ssh -L`, Tailscale), đừng đổi sang 0.0.0.0.

**Ước tính chi phí là ước tính.** Giá tham khảo trong `scripts/usage.py`, không phải hóa đơn thật. Dùng để so sánh tương đối giữa các phiên.

**Hàng rào tier là hàng rào an toàn, không phải hàng rào bảo mật.** Nó chặn AI làm bừa. Nó không chống được một tác nhân cố tình phá hoại.

**Hàng rào chỉ bảo vệ dự án đã chạy `init`.** Plugin cài toàn cục nên nó có mặt ở mọi dự án, nhưng nó cố tình đứng ngoài những dự án bạn chưa opt-in — nếu không thì nó sẽ chặn bừa ở những repo bạn không định dùng nó. Dự án nào cần bảo vệ thì phải init.
