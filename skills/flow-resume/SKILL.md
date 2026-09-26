---
name: flow-resume
description: Mo lai mot viec dang do trong AI Factory sau khi cat phien hoac sau vai ngay. Nap khi nguoi dung noi tiep mot viec cu, hoac khi inbox bao co run dang do.
user-invocable: false
---

# Mo lai viec dang do

## 1. Xem co gi

```bash
.flow/flow runs
```

Cot tien do cho biet run nao con dang do. Dau `*` la run dang mo.

## 2. Mo lai

```bash
.flow/flow resume <RUN_ID>
```

Lenh nay tra ve: da xong bao nhieu task, task ke tiep, co phieu nao dang cho
duyet, va **danh sach file phai doc lai**.

## 3. Doc lai ngu canh - khong bo qua buoc nay

Theo thu tu, doc cho den khi du hieu:

1. `handoff.md` neu co - day la ban tom tat ngan nhat, doc truoc
2. `00-idea.md` - nguoi dung ban dau muon gi
3. `02-plan.md` - ke hoach va nhung phuong an da loai bo
4. `tasks/<task_vua_xong>/notes.md` - quyet dinh ky thuat cua task truoc
5. `01-research.md` - chi doc khi sap dong vao vung chua quen

Bo buoc nay la nguyen nhan pho bien nhat khien phien sau lam lech huong phien
truoc, roi tu tao lai thu da co.

## 4. Doi chieu thuc te

File co the da lech so voi ghi chep, nhat la khi nguoi dung tu sua tay giua chung.

```bash
git log --oneline -10
git status
```

Neu co thay doi khong khop voi `tasks.json`, **hoi nguoi dung** truoc khi lam
tiep. Dung tu suy dien.

## 5. Bao cao roi moi chay

Truoc khi lam gi, noi voi nguoi dung trong 5 dong: run nay dang o dau, task ke
tiep la gi, co gi dang cho ho duyet, va co gi ban thay bat thuong.

Cho ho xac nhan roi moi chay tiep, tru khi che do tu dong dang bat.
