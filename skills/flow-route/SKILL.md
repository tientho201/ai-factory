---
name: flow-route
description: Chon tuyen chay cho mot viec trong AI Factory - chay du bon agent hay rut gon. Nap khi bat dau mot viec moi va can quyet dinh quy trinh nang hay nhe.
user-invocable: false
---

# Chon tuyen

Bon tuyen co san. Ban chon mot trong bon, khong che ra tuyen moi.

## Bang chon

Chay tu tren xuong, dung o dong dau tien khop.

| Dieu kien | Tuyen | Chay gi |
|---|---|---|
| Nguoi dung hoi de hieu, chua muon sua | **Khao sat** | `flow-explorer`, dung lai |
| Tier 2, hoac vung chua tung khao sat, hoac >5 file | **Du** | explorer -> planner -> coder -> verifier |
| 2-5 file, Tier <=1, vung da biet | **Gon** | planner -> coder -> verifier |
| 1 file, Tier 0, khong dong logic | **Nhanh** | coder -> cong may |

## Lay so lieu de chon, dung doan

```bash
.flow/flow route --files <cac file du kien> --intent "<viec can lam>"
```

Lenh nay tra ve tuyen de xuat kem ly do, dua tren: tier tinh bang luat tinh,
so file, vung da co file khao sat chua, repo co test khong.

Neu khong chac se dong den file nao, chay tuyen **Du**. Doan sai ve pham vi la
loi dat hon la chay thua mot buoc khao sat.

## Hai luat de len moi tuyen

**Tier 2 luon phai qua verifier.** Ke ca tuyen Nhanh. Neu route ra Nhanh ma
tier la 2, nang len Gon.

**Repo co test thi luon chay cong may.** Tuyen Nhanh van phai `flow.py gate`.

## Cai bay can tranh

Dung chon tuyen dua tren cam giac "viec nay don gian". Model bo qua kiem tra
dung vao luc no tu tin nhat, ma do cung la luc nguy hiem nhat. Chi dua vao
bon con so: tier, so file, vung da khao sat chua, co test khong.

Neu giua chung phat hien pham vi rong hon du kien - vi du coder bao phai sua
file ngoai danh sach - **dung lai va nang tuyen**, dung co chay tiep theo tuyen
cu.

## Chuyen mon cho tung tuyen

Agent la co dinh, nhung kien thuc nap vao chung thi khong. Khi giao viec, noi
ro agent can nap skill chuyen mon nao neu repo co:

- viec ve React/Vue -> skill quy uoc frontend cua repo
- viec cham database -> skill ve migration an toan
- viec ve API -> skill thiet ke API cua nhom

Day la cach he thong gioi them theo thoi gian: viet them skill, khong viet
them agent.
