# LoRA workflow launchers

Double-click a `.cmd` file in this folder to open the saved workflow in **Comfy Desktop**. Each launcher validates the app and source JSON path first; it never copies, edits, queues, or renders anything.

| Launcher | Verified LoRA selector(s) | Source workflow |
|---|---|---|
| `Open_MiniMax_H3_REMIX_16GB.cmd` | `FeiHouEasyH3LoraStack` | `minimaxH3REMIXModelFeihou_v20_16gb.json` |
| `Open_MiniMax_H3_REMIX.cmd` | `FeiHouEasyH3LoraStack` | `minimaxH3REMIXModelFeihou_v20.json` |
| `Open_MiniMax_H3_Turbo_LoRA.cmd` | `MiniMaxH3TurboLoRA` | `minimaxH3TurboLora.json` |
| `Open_WAN22_I2V_Quad_LoRA.cmd` | two `LoraLoaderModelOnly` nodes | WAN 2.2 I2V workflow |
| `Open_Instagirl_v23_LoRA.cmd` | four `LoraLoaderModelOnly` nodes and one `LoraLoader` | Instagirl v2.3 workflow |

Change LoRA filenames and strengths only inside the matching LoRA-loader nodes after Comfy Desktop opens the graph. Do not change an Equal Shares workflow or queue a render unintentionally.
