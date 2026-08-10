# Setup — public runner repo (~15 min, ek baar ka kaam)

**Kyun:** GitHub private repo ko sirf **2,000 minute/mahina** free deta hai — wo khatam ho gaye,
isliye robot ruk gaya. **Public repo ko unlimited free minutes** milte hain.

**Trick:** ye naya public repo me **sirf code** rahega. Robot yahan chalega, aur result
(revenue data) tumhare **purane private repo** me push karega. Tumhara **AdMob data kabhi
public nahi hoga**.

---

## ⚠️ Pehle ye check karo (sabse zaroori)

Naye repo me secrets **dobara daalne** honge — GitHub purane repo se secret ki value
dikhata nahi (security ke liye). To confirm karo ki tumhare paas ye **saved** hain:

- `ADMOB_ACCOUNTS_JSON`  ← **sabse important** (isme AdMob ke refresh token hain)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID`
- `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`

Agar `ADMOB_ACCOUNTS_JSON` save nahi hai to **ruk jao aur mujhe batao** — wo dobara banane ka
tarika alag hai (har AdMob account ka OAuth phir se karna padega).

---

## Step 1 — Naya PUBLIC repo banao

1. GitHub → upar-right **+** → **New repository**
2. Name: `admob-iq-runner`
3. **Public** chuno ✅
4. Neeche kuch add mat karo (README/gitignore nahi) → **Create repository**

## Step 2 — Files upload karo

1. Naye repo me link dikhega: **"uploading an existing file"** → us pe click
2. Is zip ko apne computer pe **unzip** karo
3. Andar ki **saari files/folders** ek saath drag-drop karo
   (`admob_iq`, `frontend`, `config`, `.github`, `requirements.txt`, `.gitignore`, `README.md`)
4. Neeche **Commit changes**

> ⚠️ Agar `.github` folder drag me na jaye (Mac chhupi files hide karta hai), to Finder me
> `Cmd + Shift + .` dabao — chhupi files dikhne lagengi.

## Step 3 — Ek token banao (private repo me push karne ke liye)

1. GitHub → **Settings** (apni profile wali) → neeche **Developer settings**
2. **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**
3. Note: `admob-iq runner`
4. Expiration: **No expiration** (ya 1 year)
5. Scope: sirf **`repo`** pe tick ✅
6. **Generate token** → token copy kar lo (ek hi baar dikhega)

## Step 4 — Secrets daalo

Naye **public** repo me → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Ye daalo:

| Secret name | Value |
|---|---|
| `DATA_REPO` | `bhanderirajdeepioo-lab/admob-iq` |
| `DATA_REPO_TOKEN` | Step 3 wala token |
| `ADMOB_ACCOUNTS_JSON` | purane repo wali same value |
| `GOOGLE_CLIENT_ID` | same |
| `GOOGLE_CLIENT_SECRET` | same |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | same |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | same (10 digit, bina dash) |
| `GOOGLE_ADS_CLIENT_ID` | same |
| `GOOGLE_ADS_CLIENT_SECRET` | same |
| `GOOGLE_ADS_REFRESH_TOKEN` | **naya banana hoga** — purana expire ho gaya (neeche dekho) |

## Step 5 — Google Ads ka naya token (ROAS ke liye)

Purana token expire ho gaya (`invalid_grant`). Permanent fix:

1. Google Cloud Console → project **adwords-iq** → **OAuth consent screen**
   → **Publish app** (Testing → In production).
   👉 **Ye pehle karo** — warna naya token bhi 7 din me expire ho jayega.
2. OAuth Playground se naya refresh token banao (pehle jaise: ⚙️ gear → "Use your own OAuth
   credentials" → apna client id/secret → scope `https://www.googleapis.com/auth/adwords`)
3. Naya token `GOOGLE_ADS_REFRESH_TOKEN` me daal do.

> ROAS ke bina bhi baaki dashboard chal jayega — ye step baad me bhi kar sakte ho.

## Step 6 — Chalu karo

1. Naye public repo → **Actions** tab → koi banner aaye to **"I understand my workflows,
   go ahead and enable them"** pe click
2. Left me **"AdMob IQ — refresh (public runner)"** → right me **Run workflow** → **Run workflow**
3. ~7 min me green ✓ aana chahiye
4. Dashboard `admob.helsyreports.com` khol ke dekho — data fresh ho gaya?

## Step 7 — Purana robot band karo

Taaki dono na takrayein aur purana fail hona band ho:

1. **Purane (private) repo** → **Actions** → left me **"AdMob IQ — hourly refresh"**
2. Right me **`...`** (teen dot) → **Disable workflow**

---

## Kuch galat ho to

Actions me red ❌ aaye to us run ko kholo, error ka screenshot bhej do. Aam wajah:

- `DATA_REPO_TOKEN` galat/expire → Step 3 dobara
- `could not clone the private data repo` → `DATA_REPO` ki spelling check karo
- `OAuth fail` → Google Ads ka token (Step 5)

## Tumhara data safe kyun hai

- Is public repo me **sirf code** hai — koi revenue data nahi
- `.gitignore` `data/`, `site/`, `config/*.json` ko block karta hai
- Workflow ko is repo pe **write permission hi nahi** hai (`contents: read`)
- Build ke logs **band** kar diye hain (public repo pe logs sabko dikhte hain)
- Secrets GitHub me encrypted rehte hain — kisi ko dikhte nahi, aur fork/PR ko milte nahi
