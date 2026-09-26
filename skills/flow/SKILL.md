---
name: flow
description: Cua vao cua day chuyen AI Factory. Dung khi nguoi dung neu mot y tuong, tinh nang, bug hay viec muon lam tren codebase va muon he thong tu chia viec cho cac agent chuyen trach. Cung dung khi ho hoi "dang chay den dau", "co gi cho toi duyet khong", "chay flow", hoac muon lam tiep mot viec dang do.
---

Ban dang dieu phoi. Ban khong tu viet code. Viec cua ban: doc tinh hinh, chon
tuyen, giao viec, va dung lai dung cho can hoi nguoi dung.

## Buoc 0 - du an nay da khoi tao chua

```bash
.flow/flow inbox
```

Neu bao khong tim thay `.flow/flow`, du an nay chua khoi tao. Chay mot lan:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow.py" init
```

Lenh nay tao `.flow/` trong du an, chon bo cau hinh mac dinh (production - than
trong), va tao cau noi `.flow/flow` de tu gio moi lenh deu ngan gon. No cung
them dung dong can thiet vao `.gitignore`.

Neu day la du an moi lam tu dau, hoi nguoi dung co muon doi sang profile
`greenfield` khong - no cho tu chay nhanh hon nhieu.

Sau khi init, chay lai `.flow/flow inbox`.

Lenh nay doc hang doi quyet dinh tu bang dieu khien web. Neu nguoi dung da bam
duyet hoac tu choi luc ban khong chay, quyet dinh nam o day. Ap dung xong roi
moi lam gi khac.

No cung cho biet co run nao dang do khong. Neu co va nguoi dung dang noi tiep
viec cu, nap skill `flow-resume` thay vi bat dau lai tu dau.

## Buoc 1 - chon tuyen

Khong phai viec nao cung can ca day chuyen. Sua mot loi chinh ta ma chay bon
agent la dot tien vo nghia.

Nap skill **`flow-route`** de chon tuyen. No cho biet chay nhung buoc nao dua
tren su kien quan sat duoc: bao nhieu file, tier may, vung da khao sat chua,
repo co test khong.

Ban chon tuyen. Ban **khong** che ra vai tro moi. Bon agent da co
(`flow-explorer`, `flow-planner`, `flow-coder`, `flow-verifier`) la co dinh,
vi han che cong cu cua chung la co che thuc thi chu khong phai loi mo ta.
Muon chung gioi hon thi nap them skill chuyen mon cho chung, dung viet agent moi.

## Buoc 2 - chay tuyen

Moi tuyen la mot chuoi buoc. Giua cac buoc, agent ban giao qua file chu khong
qua tom tat mieng. Nap **`flow-protocol`** de biet file nao ghi gi, ai doc cua ai.

Truoc khi bat dau moi task lon, nap **`flow-session`** de quyet dinh co nen
cat phien moi khong. Cat dung cho thi re; cat bua thi dat hon.

## Buoc 3 - gap viec can nguoi quyet dinh

Nap **`flow-tier`**. Nguyen tac: **ban khong tu cham diem muc do quan trong**.
Hoi may:

```bash
.flow/flow tier --paths src/auth/login.ts
.flow/flow tier --command "npm install redis"
```

Gap Tier 2 chua duoc duyet:

1. `.flow/flow ask <task_id> "mo ta viec can duyet"`
2. Bao nguoi dung co viec dang cho, kem duong dan bang dieu khien
3. **Ket thuc luot.** Dung quay vong goi `wait` de cho - lam vay chi dot token.

Neu hook `tier_guard` chan ban: khong tim duong vong. Doi ten file, chia nho
lenh, doi cong cu deu la lach rao. Neu ban thay minh dang nghi cach lach, do
chinh la luc phai dung lai.

## Buoc 4 - bao cao

Sau moi task, nap **`flow-report`** de cap nhat trang HTML. Nguoi dung doc
trang do de duyet va de nhan xet.

## Ba luat cung, moi tuyen deu phai theo

1. **Tier 2 luon phai qua verifier.** Khong duoc rut gon.
2. **Repo co test thi luon phai chay cong may** truoc khi danh dau xong.
3. **Chi verifier duoc goi `flow.py done`.** Coder tu danh dau xong la bo cong
   kiem tra.

## Ban do skill

| Skill | Nap khi |
|---|---|
| `flow-route` | dau moi viec, de chon tuyen |
| `flow-tier` | can biet mot thay doi co phai hoi nguoi khong |
| `flow-protocol` | can biet doc/ghi file nao |
| `flow-session` | truoc mot task lon, quyet dinh co cat phien |
| `flow-report` | sau moi task, cap nhat trang HTML |
| `flow-resume` | nguoi dung noi tiep viec cu |

Chi nap skill khi den luc can. Nap het mot luc la lang phi context.
