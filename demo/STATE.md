# Cinemory — submission state

_Last updated: 2026-07-04. Deadline: 2026-08-03 5:00pm EDT. $10k. Greece-eligible._

## Where it stands: ~92/100 (code/docs complete; live-run + video are owner-only)

The former 95-blocker — "Genblaze adapter untested vs the real SDK" — is **closed**:
the adapter is verified against the real published Genblaze SDK and contract-tested
in CI. See `feat/genblaze-adapter-contract` (PR).

### Scorecard vs the 4 Devpost criteria
| Criterion | Before | After | Note |
|---|---|---|---|
| Real-World Utility | 8.5/10 | 8.5/10 | consumer + B2B event wedge; unchanged |
| Production Readiness | 8/10 | 9/10 | +SDK contract test; 68 tests; drift guarded |
| B2 Storage & Orchestration | 8.5/10 | 9/10 | two real B2 write paths (Genblaze sink + cinemory) |
| Use of Genblaze | 6/10 | 8.5/10 | load-bearing (gen+sink+manifest); sink→store→readback path covered offline, SDK-verified |

Ceiling to 95+ is gated on the live app URL + demo video, which need credentials.

## Verified against the real SDK (genblaze-core 0.3.4 / -s3 0.3.4 / -gmicloud 0.3.2)
- `Pipeline().step(provider, model=, prompt=, modality=, **params).run(sink=, timeout=, raise_on_failure=True)` ✓
- `PipelineResult(run, manifest)`; `result.run.steps[-1].assets[0]` ✓
- `Asset` is **URL-addressed** (`url`/`sha256`/`size_bytes`/`media_type`) — no `.read()/.bytes` (old adapter bug, fixed) ✓
- `S3StorageBackend.for_backblaze(bucket, region=, key_id=, app_key=)` reads `B2_BUCKET/B2_REGION/B2_KEY_ID/B2_APP_KEY` ✓
- `ObjectStorageSink(backend, ...)`, `KeyStrategy.{HIERARCHICAL,CONTENT_ADDRESSABLE}` ✓
- `genblaze_gmicloud.GMICloud{Video,Image,Audio}Provider` ✓
- `manifest.verify_hash()` ✓

## Owner action list (all require the owner's own credentials — cannot be faked)
1. Fill `.env`: `B2_BUCKET_NAME`, `B2_REGION`, `B2_KEY_ID`, `B2_APP_KEY`, `GMI_API_KEY`
   (GMI Cloud gives first ~270 credits free).
2. `pip install -e ".[live]"` then `CINEMORY_MODE=live bash demo/capture-demo.sh` — one live reel to B2.
3. Deploy the container to **cinemory.ai** (Dockerfile ready) and confirm the judge URL.
4. Record the ~3-min video (`demo/video-script.md`).
5. Submit the Devpost form (see `demo/SUBMISSION.md` for every field, incl. model list).

## No live-run results are claimed anywhere without credentials.
