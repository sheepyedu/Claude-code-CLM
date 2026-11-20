#!/bin/bash
mkdir -p /logs/verifier
if test "$(cat /tmp/remembered 2>/dev/null)" = apricot; then echo 1; else echo 0; fi > /logs/verifier/reward.txt
