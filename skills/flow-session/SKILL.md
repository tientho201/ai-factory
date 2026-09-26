---
name: flow-session
description: Quyet dinh co nen cat phien Claude moi truoc mot task de tiet kiem token. Nap truoc khi bat dau mot task lon trong AI Factory.
user-invocable: false
---

# Cat phien moi hay chay tiep

Moi luot trong mot phien phai gui lai toan bo lich su. Phien chay den task thu
sau dang cong ca nam task truoc, du chung khong lien quan. Cat phien la vut
ganh do di.

Lam duoc dieu nay **chi vi** he thong ban giao qua file. Phien moi khong mat
ngu canh - no doc lai `01-research.md`, `02-plan.md`, `notes.md`.

## Cai bay

Phien moi cung phai nap lai dong file do, va no vut luon prompt cache dang am.
Voi task nho, cat phien **dat hon** la chay tiep. Nen phai co nguong.

## Khi nao cat

Cat khi **it nhat hai** dieu sau dung:

- Task ke tiep khong doc truc tiep ket qua task vua roi
- Phien hien tai da dung qua nua context (xem `/context`)
- Task vua xong la task lon (tren 3 file, hoac tren 10 luot)
- Sap chuyen sang mot vung code khac han

## Khi nao dung cat

- Task ke tiep dung truc tiep thu task truoc vua tao ra
- Ca hai task deu nho
- Dang giua mot vong sua loi (coder <-> verifier qua lai)
- Phien moi bat dau, context con rong

## Cat the nao

```bash
.flow/flow hand-off <task_id>
```

Lenh nay ghi `.flow/runs/<run>/handoff.md` - mot trang duy nhat chua tat ca
nhung gi phien sau can biet: dang lam den dau, task ke tiep la gi, doc file nao,
quyet dinh nao da chot, cho nao con vuong.

Sau do bao nguoi dung:

> Task T3 xong roi. Nen cat phien moi cho T4 vi <ly do>. Ban go `/clear` roi
> nhan "tiep tuc T4", toi se doc lai handoff.md.

**Khong tu chay `/clear`.** Do la quyet dinh cua nguoi dung, vi ho co the con
muon hoi lai ve nhung gi vua lam.

## Phien moi bat dau the nao

Buoc dau tien cua phien moi luon la:

```bash
.flow/flow inbox
cat .flow/runs/<run_id>/handoff.md
```

Doc xong moi lam. Dung doan lai tu dau.

## Do luong

```bash
.flow/flow usage
```

Cho biet phien nay da dung bao nhieu token, uoc tinh chi phi, va so sanh voi
cac phien truoc. Trang bao cao HTML cung hien so nay de ban tu thay khi nao
nen cat.
