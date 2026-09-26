---
name: flow-report
description: Ghi bao cao cuoi moi task de nguoi dung doc, duyet va nhan xet tren trang web. Nap sau khi verifier xong mot task, hoac khi nguoi dung muon xem bao cao.
user-invocable: false
---

# Bao cao cho nguoi doc

Bang dieu khien web doc truc tiep tu file, khong can dung script gi de "dung
trang". Ban chi can ghi dung file, dung cho.

```bash
.flow/flow dashboard
```

## Ba file lam nen bao cao

| File | Ai ghi | Hien o dau |
|---|---|---|
| `tasks/<id>/review.md` | verifier | muc "Verifier ket luan" |
| `tasks/<id>/notes.md` | coder | muc "Coder ghi lai" |
| `tasks/<id>/gate.json` | `flow.py gate` | day chip ket qua test |

Nguoi dung bam vao mot task tren trang la thay ca ba.

## Viet cho nguoi doc, khong viet cho may

Nguoi dung doc bao cao nay de **quyet dinh**, khong phai de thuong thuc. Nen:

- Cau ket luan len dau. `## Ket luan: CHO QUA` hoac `## Ket luan: TRA LAI`
  phai o vi tri de thay - trang web cat tu cho nay de hien.
- Noi cai dang lo truoc cai da on. Nguoi ta doc ba dong dau roi luot.
- Neu co gi may khong kiem duoc ma ban thay ngo ngo, **noi ra**. Do la gia tri
  lon nhat cua ban o buoc nay; phan con lai cong may da lam roi.
- Dung liet ke lai nhung gi da co trong `gate.json`. Trang web hien no roi.

## Nhan xet cua nguoi dung

Nguoi dung go nhan xet vao o tren trang. No vao `tasks/<id>/feedback.md` va
vao hang doi.

**Truoc khi sua lai mot task bi tra ve, luon doc `feedback.md` truoc.** Nhan
xet cua nguoi dung de len tren ket luan cua verifier - ho biet thu ma ca hai
ban deu khong biet.

Neu nhan xet mau thuan voi ke hoach ban dau, dung im lang lam theo. Noi ro cho
ho biet cho mau thuan, roi hoi.

## Sau moi task lon

Ghi ban giao de phien sau doc:

```bash
.flow/flow hand-off <task_id>
```

Xem `flow-session` de biet khi nao nen khuyen nguoi dung cat phien moi.
