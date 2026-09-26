---
name: flow-protocol
description: Cau truc thu muc .flow va hop dong ban giao giua cac agent trong AI Factory - file nao ghi gi, ai doc cua ai. Nap khi lam viec voi .flow, khi can biet doc file nao de lay context, hoac khi agent truoc da lam gi.
user-invocable: false
---

# Hop dong ban giao

Agent khong truyen tom tat cho nhau. Moi agent ghi ra file, agent sau doc file.
Ly do: tom tat truyen tay mat thong tin o moi lan chuyen giao. File thi khong,
va nguoi dung doc duoc no.

## Cau truc

```
.flow/
  config.json              luat tier, che do tu dong, gioi han
  current.json             run_id + task_id dang chay
  runs/<run_id>/
    00-idea.md             y tuong goc         <- flow.py start ghi
    01-research.md         khao sat            <- flow-explorer ghi
    02-plan.md             ke hoach dang van   <- flow-planner ghi
    tasks-draft.json       ke hoach tho        <- flow-planner ghi
    tasks.json             ke hoach chinh thuc <- flow.py plan-import ghi
    state.json             pha hien tai
    events.jsonl           nhat ky khong xoa duoc
    approvals/<task>.json  phieu cho duyet
    handoff.md             ban giao giua hai phien Claude
    report.html            trang bao cao nguoi dung doc
    tasks/<task_id>/
      notes.md             quyet dinh ky thuat <- flow-coder ghi
      gate.json            ket qua cong may    <- flow.py gate ghi
      review.md            ket qua review      <- flow-verifier ghi
```

## Ai doc cua ai

| Agent | Doc | Ghi |
|---|---|---|
| explorer | `00-idea.md` | `01-research.md` |
| planner | `00-idea.md`, `01-research.md` | `02-plan.md`, `tasks-draft.json` |
| coder | `tasks.json`, `01-research.md` | code + `notes.md` |
| verifier | tat ca tren + `notes.md`, `gate.json` | `review.md` |

Bo mot buoc doc la mat context. Day la loi thuong gap nhat trong kien truc nay.

## tasks.json

```json
{
  "run_id": "20260918-1430-a1b2",
  "tasks": [{
    "id": "T1",
    "title": "...",
    "description": "...",
    "files": ["src/a.ts"],
    "depends_on": [],
    "parallel_group": 1,
    "tier": 1,
    "tier_reason": "khong khop luat nao, dung tier mac dinh",
    "acceptance": ["npm test -- a pass"],
    "status": "pending",
    "attempts": 0
  }]
}
```

`files` la **quyen so huu**. Hai task cung `parallel_group` khong duoc trung
file. Coder chi duoc ghi vao file trong danh sach cua no.

`status` di theo: `pending` -> `running` -> `done`, re nhanh sang
`awaiting_approval`, `gate_failed`, `review_failed`, `blocked`, `skipped`.

## Quy tac cung

- **Khong bao gio sua `tasks.json` bang tay.** Dung `flow.py`. Sua tay lam
  lech trang thai so voi phieu duyet.
- **Chi verifier duoc goi `flow.py done`.** Coder tu danh dau xong la bo cong
  kiem tra.
- **`events.jsonl` chi them, khong sua.** Do la nhat ky that de doi chieu khi
  agent ke sai.
- Moi khi bat dau mot buoc, `cat .flow/current.json` de biet minh o dau.
  Dung nho trong dau.
- **Hang doi `.flow/queue/`** chua quyet dinh nguoi dung bam tren trang web luc
  ban khong chay. Luon chay `flow.py inbox` truoc khi lam gi khac.
- **Nhan xet cua nguoi dung** tren trang bao cao vao `tasks/<id>/feedback.md`.
  Doc file nay truoc khi sua lai mot task bi tra ve.
