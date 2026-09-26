# 2026-09-11g — C002 v3 fail; arm two-pass v4a/v4b

## v3 result
- Attempt e6d13d26200a4476bf8362d45e542dcc
- SHA-256 0ddefb4963865da70c9a6352ed50ca1545bb0209b00f168108beb853ae4869d
- Bright-teal metric ~0, but visual: dark-green polygonal blob + detached hand/cloth
- Continuity identity/room held; semantic fail (pose/cloth)
- Production paused after max_attempts=1

## Strategy shift
Single-pass erase+arm keeps failing the raised-hand hole. Implement **two-pass**:
- **v4a** c002-raised-hand-erase-v4a: raised-hand-only mask → sofa/wall fill (no OpenPose)
- **v4b** c002-hanging-arm-openpose-v4b: hanging-arm corridor on the v4a plate + OpenPose

## Next
One supervisor run; expect v4a then automatic v4b. Visual QA required. Still-only.
