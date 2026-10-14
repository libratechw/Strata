#!/bin/bash
# After the 4K A/B: fresh-start 4K x10 with each of the two documented workarounds (default sysctl), counters as in vm-0-*.
H=/data/ssd/llm-experiments/gdn-chunk-20261012
until [ -f $H/e4k.done ]; do sleep 30; done
cd $H
DELAYS=0 PREFIX=pinxfer EXTRA_ENV="STRATA_PREFILL_TIMING=1 GPU_PINNED_MIN_XFER_SIZE=1048576" scripts/delay4k3.sh 10
DELAYS=0 PREFIX=nouserptr EXTRA_ENV="STRATA_PREFILL_TIMING=1 HSA_USERPTR_FOR_PAGED_MEM=0" scripts/delay4k3.sh 10
touch $H/workaround4k.done
