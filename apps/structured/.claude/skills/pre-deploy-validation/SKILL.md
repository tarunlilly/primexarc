---
name: pre-deploy-validation
description: Use this skill before pushing or deploying ARC to verify the frontend
  build is correctly configured. Triggers on "ready to push", "test before deploy",
  "validate the build", "is this ready to merge", "check before pushing",
  "ready to deploy". Important when changes touch auth config, env vars,
  Dockerfile, or MSAL files.
version: 1.0.0
user-invocable: true
tools: Read, Bash, Agent
---

# Pre-Deploy Validation (apps/structured)

Run these steps in order. All paths relative to `apps/structured/`.
Stop and report if any step fails.

## 1. Check .env.local is set up

```bash
cat apps/structured/frontend/.env.local 2>/dev/null || echo "MISSING"
```

- If missing: tell user to copy `.env.local.example` and fill in `VITE_CLIENT_ID`
  and `VITE_TENANT_ID` from Azure Portal.
- If present but values empty: report which vars are empty.
- If both values present: proceed.

## 2. Verify auth.js hasn't regressed

Check `frontend/src/lib/auth.js`:
1. No hardcoded client ID strings (no GUIDs, no 'dev-bypass')
2. `clientId` reads from `import.meta.env.VITE_CLIENT_ID`
3. `DEV_BYPASS` and `MISSING_CONFIG` flags are exported
4. No MSAL imports in files other than auth.js, main.jsx, App.jsx, Layout.jsx, user.js, api.js

Report: PASS or FAIL with specific line numbers.

## 3. Run the build with validation

```bash
cd apps/structured/frontend && npm run build 2>&1
```

- `prebuild` hook runs `validate-build.mjs --pre` first (fails if env vars missing).
- Full Vite build runs next.
- Report build output. If it fails, show exact error.

## 4. Verify bundle contents

```bash
cd apps/structured/frontend && npm run verify-bundle 2>&1
```

This greps `dist/assets/*.js` for the actual `VITE_CLIENT_ID` value.
- PASS: "bundle OK" message
- FAIL: client ID not found in bundle

## 5. Check nothing sensitive is staged

```bash
git diff --cached --name-only
```

Fail if any of these are staged:
- `.env.local`
- `.npmrc`
- Any file containing a raw GUID matching the CLIENT_ID pattern

## 6. Check Dockerfile paths are valid

Verify `frontend/Dockerfile` and `backend/Dockerfile` COPY/ADD paths resolve
correctly from `apps/structured/` as the build context.

## 7. Final report

Summarize each step as PASS / FAIL / SKIP with one line of detail.
If all steps pass, tell the user the build is verified and safe to push.
If any step fails, tell them exactly what to fix.

## Local SSO testing (manual step)

If the user wants to test the actual Azure AD login flow:
1. Confirm `.env.local` has real values
2. `cd apps/structured/frontend && npm run dev`
3. Open `http://localhost:5173`
4. Sign in with Lilly credentials
5. Header should show real name/email
6. "Sign out" should trigger Azure AD logout

This requires human interaction and cannot be automated.
