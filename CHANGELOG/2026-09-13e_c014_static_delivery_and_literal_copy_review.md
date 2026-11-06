# 2026-09-13e — C014 static delivery wording and literal-copy review repair

## Root cause

The C014 v2 output was byte-identical to its accepted C013 reference and the
blind inspector reported no visible camera/tripod plus complete continuity.
It nevertheless failed before semantic acceptance because its derived prompt
used the action verb “leans,” which the deterministic still gate rejects.  The
structured VLM response also omitted its required containers and repeated the
unsupported camera claim.

## Change

The C014 recovery is now v3:

- The derived delivery prompt is static: a crouched adult man with hands set on
  an unseen lower-edge support.  It does not name or show a camera and it does
  not instruct motion.
- A narrowly scoped schema repair is allowed only for C014-start when the
  candidate is byte-identical to its supplied reference, independent blind
  evidence says no equipment is visible, and the structured reviewer is empty,
  incomplete, or makes the specific unsupported camera claim.  The standard
  blind and full continuity checks still execute; this is not a general QA
  bypass.

The canonical source prompt remains hash-bound in every receipt.  The v1/v2
attempts and their failures are preserved.

## Verification

The runner compiled and all 114 targeted tests passed.  No GPU task or video
job started during the patch/test pass.
