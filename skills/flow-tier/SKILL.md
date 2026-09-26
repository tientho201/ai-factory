---
name: flow-tier
description: Luat phan cap rui ro cua AI Factory - viec nao tu chay duoc, viec nao bat buoc phai hoi nguoi dung. Nap khi can quyet dinh co duoc tu lam mot thay doi hay khong, khi gap hang rao tier guard, hoac khi nguoi dung hoi ve nguong duyet.
user-invocable: false
---

# Phan cap rui ro

Phan loai theo **loai hanh dong**, khong theo muc do tu tin cua model.
Model sai dung vao luc no chac chan nhat, nen no khong duoc tu cham diem minh.

## Ba muc

**Tier 0 - tu chay, khong can bao.**
Test, tai lieu, comment, sua chinh ta, format, lint fix, CSS thuan tuy,
file trong `.flow/`. Hong thi chi ton thoi gian, khong mat gi.

**Tier 1 - tu chay roi bao cao lai.** Day la mac dinh.
Them tinh nang trong module da co, refactor noi bo khong doi public API,
sua bug trong pham vi mot module. Hong thi git revert duoc.

**Tier 2 - bat buoc nguoi duyet truoc.**
Migration va schema database. Auth, phan quyen. Thanh toan, billing.
Them hoac nang dependency. Secret, bien moi truong, credential.
Config ha tang: Dockerfile, CI, terraform, k8s, nginx.
Doi public API hoac hop dong giua cac module.
Xoa file. Git push, git reset --hard, git rebase.
Lenh cham vao he thong that: kubectl, terraform apply, psql, aws, deploy.

Diem chung cua Tier 2: hong thi khong revert lai duoc bang mot lenh git,
hoac anh huong ra ngoai repo.

## Cach hoi

Dung tu suy luan. Hoi may:

```bash
.flow/flow tier --paths src/auth/session.ts
.flow/flow tier --command "pnpm add redis"
.flow/flow tier --text "them cot email vao bang users"
```

Tra ve `tier`, `reason`, va `needs_human` - da tinh ca che do tu dong.

## Khi bi chan

Hook `tier_guard.py` chan bang exit code 2. Khi thay thong bao do:

1. **Khong lach.** Doi duong dan, tach lenh thanh nhieu buoc nho, chuyen sang
   cong cu khac - tat ca deu la lach rao, va deu se bi chan lai.
2. Chay `.flow/flow wait <task_id>` de cho nguoi bam duyet.
3. Hoac de xuat mot cach lam khac khong cham vao vung Tier 2.
4. Hoac bao cao lai va dung.

## Hai bo cau hinh san

Luat nam trong `.flow/config.json`. Co hai profile dat san trong `profiles/`:

```bash
.flow/flow profile production   # codebase dang chay that
.flow/flow profile greenfield   # du an moi, hong thi vut duoc
.flow/flow profile             # xem dang dung cai nao
```

`production`: auto tat, Tier 2 rong, moi thu thien ve than trong.
`greenfield`: auto bat den Tier 2, chi chan nhung thu cham ra ngoai repo.

Doi profile la viec cua nguoi dung. Neu ban thay profile hien tai khong hop voi
viec dang lam, **de xuat** doi, dung tu doi.

## Sua luat

Tier cao nhat khop duoc thang. Tier cua mot task la tier cua file nguy hiem
nhat trong task do. Khong khop gi thi la `default_tier`.

Chi nguoi dung sua `tier_rules`. Thay luat gay phien thi de xuat, dung tu sua.
