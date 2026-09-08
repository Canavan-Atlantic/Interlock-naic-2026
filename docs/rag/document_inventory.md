# INTERLOCK RAG document inventory

This is a file-organisation inventory only. No embeddings, chunking, retrieval, vector store, policy interpretation, or indexing implementation was performed.

## Created structure

```text
data/rag/
├── primary/
│   ├── ireland/
│   │   ├── government/
│   │   ├── eirgrid/
│   │   ├── cru/
│   │   │   ├── current/
│   │   │   └── historical_proposed/
│   │   ├── water/
│   │   └── planning/
│   │       ├── national/
│   │       ├── regional/
│   │       └── local_authority/
│   │           └── fingal/
│   └── eu/
│       ├── biodiversity/
│       └── energy/
├── curated/
│   └── ireland_datacentre_screening/
├── supporting/
│   ├── public_bodies/
│   │   └── cru_consultation/
│   ├── industry/
│   │   └── cru_consultation/
│   └── research/
│       ├── eu_policy_context/
│       ├── eu_energy/
│       └── screening/
├── governance/
│   └── responsible_ai/
├── restricted/
│   └── confidential_research/
└── archive/
    ├── cru_consultation/
    └── original_packages/

docs/rag/
scripts/rag/
```

Empty primary folders are intentional: no duplicate EirGrid, water, current CRU, or planning source files were created.

## Active retained documents

`SHA-256` values are calculated from the copied destination files. `Index later?` is a planning flag only; it does not mean indexing has been implemented.

| Filename | Destination | Source package | Classification | SHA-256 | Index later? | Notes |
|---|---|---|---|---|---|---|
| government-statement-on-the-role-of-data-centres-in-irelands-enterprise-strategy.pdf | `data/rag/primary/ireland/government/government-statement-on-the-role-of-data-centres-in-irelands-enterprise-strategy.pdf` | Standalone source file | PRIMARY | E28607C20578F4578C058CF8E27A0D2844CC4B0742773B7D4570374263A4B6A1 | YES | — |
| leap-large-energy-user-action-plan.pdf | `data/rag/primary/ireland/government/leap-large-energy-user-action-plan.pdf` | Standalone source file | PRIMARY | 0673B3AB0A49FAEACE0AB8432DD1D64082F69B04A0CB236FD4A0B8A13098C6A9 | YES | — |
| an-economic-assessment-of-green-energy-park-concepts.pdf | `data/rag/restricted/confidential_research/an-economic-assessment-of-green-energy-park-concepts.pdf` | Standalone source file | RESTRICTED | 818C01629383112D50E99D1DE8E05BD3E17D2FF30348C8BC9B0AF594B14D230F | NO pending access/review | CONFIDENTIAL |
| CRU202504 LEU connection policy proposed decision_0.pdf | `data/rag/primary/ireland/cru/historical_proposed/CRU202504 LEU connection policy proposed decision_0.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | PRIMARY | 765E9F1988AA3A62B46D32B30AB78C0D9F1EC011621C3B08E51306312B49E9C1 | YES | PROPOSED; HISTORICAL; not current final policy |
| CRU202504v - EirGrid_1.pdf | `data/rag/supporting/public_bodies/cru_consultation/CRU202504v - EirGrid_1.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_PUBLIC_BODY | 7CF47BEA5028F495ED3F2CD479F30AF460EFF95326D0BAAF5F3E3400A8CFCC0C | YES | — |
| CRU202504z - ESBN.pdf | `data/rag/supporting/public_bodies/cru_consultation/CRU202504z - ESBN.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_PUBLIC_BODY | 99C27030EFCD5E487DEFB2FEBA996FEAFDB25B89B532693D41E176CB02A97101 | YES | — |
| CRU202504l - DETE.pdf | `data/rag/supporting/public_bodies/cru_consultation/CRU202504l - DETE.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_PUBLIC_BODY | 73FB1135822A27B8538D4E6520B75F752AC1D7866F7FF1454C60567E59088847 | YES | — |
| CRU202504ap - GNI.pdf | `data/rag/supporting/public_bodies/cru_consultation/CRU202504ap - GNI.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_PUBLIC_BODY | 5F9AA5E4F72D9E10FDC837611DB9A3174AE9063C41A4FC2D1174D14BCF9FB35A | YES | — |
| CRU202504an - Uisce Eireann.pdf | `data/rag/supporting/public_bodies/cru_consultation/CRU202504an - Uisce Eireann.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_PUBLIC_BODY | 00FE376D0A3E6F340DBC5A0A933563E629924222738EBEB4DC15CBA57F25D485 | YES | — |
| CRU202504r - Enterprise Ireland_1.pdf | `data/rag/supporting/public_bodies/cru_consultation/CRU202504r - Enterprise Ireland_1.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_PUBLIC_BODY | 3995830098BA542168661ABB25F18D1EC62F391937D6DA5229ED02548401CA9D | YES | — |
| CRU202504aj - Irish Planning Institute.pdf | `data/rag/supporting/public_bodies/cru_consultation/CRU202504aj - Irish Planning Institute.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_PUBLIC_BODY | 0AC7F93D0B5051A740C293615796D9FDD3DBD1EAEEAB603F108200D676F1B369 | YES | — |
| CRU202504ac - Equinix.pdf | `data/rag/supporting/industry/cru_consultation/CRU202504ac - Equinix.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_INDUSTRY | B73DB39B8AF7E0ED8447F00C317ED43FDB496C7B03E94911D4704D11FD473646 | YES | — |
| CRU202504k - CyrusOne.pdf | `data/rag/supporting/industry/cru_consultation/CRU202504k - CyrusOne.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_INDUSTRY | 9FF4BD0595E975CDC49E7E5DF865ED617C8556D57BE51D5F51A49734980A29DF | YES | — |
| CRU202504ah - IBEC.pdf | `data/rag/supporting/industry/cru_consultation/CRU202504ah - IBEC.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_INDUSTRY | 724A3265312043085EEDD4EDC059ECA39BE3A65EF78B11173C72F91C63264852 | YES | — |
| CRU202504a - AmCham.pdf | `data/rag/supporting/industry/cru_consultation/CRU202504a - AmCham.pdf` | CRU connections policy-20260907T221318Z-1-001.zip | SUPPORTING_INDUSTRY | E69115D5BD51C727EC667BFC458859061CE1B7D6EC95F3E130AA498D1814ACAB | YES | — |
| Birds Directive - Environment - European Commission.pdf | `data/rag/primary/eu/biodiversity/Birds Directive - Environment - European Commission.pdf` | Regulations-20260907T183130Z-1-001.zip | PRIMARY | 067204888372FCC546A1F95C412814289343C24C445427A05D7171C927195949 | YES | — |
| Renewable Energy Directive.pdf | `data/rag/primary/eu/energy/Renewable Energy Directive.pdf` | Regulations-20260907T183130Z-1-001.zip | PRIMARY | EE62BB345E5987351E0883326D7EB2E45BF003E4F7B1EFA7F2B5936234461C93 | YES | — |
| Biodiversity Strategy for 2030 - Environment - European Commission.pdf | `data/rag/supporting/research/eu_policy_context/Biodiversity Strategy for 2030 - Environment - European Commission.pdf` | Regulations-20260907T183130Z-1-001.zip | SUPPORTING_RESEARCH | B6B6B1B24C4B5634D07B105967A302ADB150114DF54E8890854C77251DC32B57 | YES | — |
| New impetus for energy efficiency - European Commission.pdf | `data/rag/supporting/research/eu_energy/New impetus for energy efficiency - European Commission.pdf` | Regulations-20260907T183130Z-1-001.zip | SUPPORTING_RESEARCH | BFD4807B8EB6A8CE4DC6F729F8485E40BCDBAEBC3722691697625F11BEBA91C7 | YES | — |
| EU AI Act - DETE.pdf | `data/rag/governance/responsible_ai/EU AI Act - DETE.pdf` | Regulations-20260907T183130Z-1-001.zip | GOVERNANCE | 2F8301A0316B4B971EDBFED36D0EA0CB130F8521C1847B2D6DC4F5BCF26A5D94 | NO | Responsible AI governance; not site-assessment policy RAG |
| rag_records.jsonl | `data/rag/curated/ireland_datacentre_screening/rag_records.jsonl` | Meng Report-20260907T182546Z-1-001.zip | CURATED | EAEA55838A06F2AA6156649A05EE879997DCCD04B71B1E8AB022F7C09DF585C0 | YES | Curated records; candidate for later site-assessment RAG indexing |
| source_registry.json | `data/rag/curated/ireland_datacentre_screening/source_registry.json` | Meng Report-20260907T182546Z-1-001.zip | CURATED | F686A009B12A327301434BFAB326BFE2DF70671083918F382D020F4B4FB6986A | NO | Source metadata; not policy evidence |
| review_flags.jsonl | `data/rag/curated/ireland_datacentre_screening/review_flags.jsonl` | Meng Report-20260907T182546Z-1-001.zip | CURATED | E21D5FBF732A9323F6DFB63E73D9B520CAEECD7DA52FCAE4A550CB91FDF07DBB | NO | Review metadata; not policy evidence |
| rag_record_schema.json | `data/rag/curated/ireland_datacentre_screening/rag_record_schema.json` | Meng Report-20260907T182546Z-1-001.zip | CURATED | 31101E059EC5EC380ACE7A35C5C6DE6B0F55553A18FCFC02C812A6F5E9B9064F | NO | Schema; not policy evidence |
| retrieval_eval_cases.jsonl | `data/rag/curated/ireland_datacentre_screening/retrieval_eval_cases.jsonl` | Meng Report-20260907T182546Z-1-001.zip | CURATED | 7DBF7312F2BC8201D576BEEB02FAA9EC7FF891A9D380911C3A0D9F54E093E109 | NO | Evaluation cases; not policy evidence |
| rag_design.md | `docs/rag/rag_design.md` | Meng Report-20260907T182546Z-1-001.zip | CURATED | 8064B25233E1895CC6794F1CCDB8C8D1D318253E26DAB8A1CC672ECB6FD093BA | NO | Design documentation; not policy evidence |
| transformation_audit.md | `docs/rag/transformation_audit.md` | Meng Report-20260907T182546Z-1-001.zip | CURATED | C11AB2C665C4AA6750DAED0C0FF69360FB8C33CB2AE1F059D88C0826FC449F1F | NO | Transformation audit; not policy evidence |
| validate_rag.py | `scripts/rag/validate_rag.py` | Meng Report-20260907T182546Z-1-001.zip | CURATED | 4682C72DE9E8F32AD954FED78DDFAB8EA9F29655BD2D547A4314C84D05E87330 | NO | Validation utility; not policy evidence |
| convert_to_english.py | `scripts/rag/convert_to_english.py` | Meng Report-20260907T182546Z-1-001.zip | CURATED | F343F6D27208A0F922C06FAD13FA3722903FB2CCC010D329C07709F2A631171E | NO | Optional conversion utility; not policy evidence |
| ireland datacenter screening data.pdf | `data/rag/supporting/research/screening/ireland datacenter screening data.pdf` | Meng Report-20260907T182546Z-1-001.zip | SUPPORTING_RESEARCH | 00386BD086E2517F87CD7B6998A7D1FDCBF4F9A1B234FDE050CB544C7A18978C | YES | One active copy retained; identical nested screening PDF skipped |

## Original packages retained in archive

| Package | Destination | SHA-256 | Notes |
|---|---|---|---|
| CRU connections policy-20260907T221318Z-1-001.zip | `data/rag/archive/cru_consultation/CRU connections policy-20260907T221318Z-1-001.zip` | 2DE0EC76D7C7A27DB535AD396125E227440FFBABF8D9128827293FF49FED165B | Complete original ZIP; all unselected consultation responses remain inside it |
| Regulations-20260907T183130Z-1-001.zip | `data/rag/archive/original_packages/Regulations-20260907T183130Z-1-001.zip` | 8F395BECA0ECFBBDB75D1809EE9B5BE21DCBDBF90FA596B223665600608C9BEB | Complete original ZIP |
| Meng Report-20260907T182546Z-1-001.zip | `data/rag/archive/original_packages/Meng Report-20260907T182546Z-1-001.zip` | 4FD933C35FA4E1381C75F78F1C2C36F8A04957B45EEC399EF663CA459ABA111E | Complete original ZIP, including nested curated package |

## Duplicate handling

| File | SHA-256 | Result |
|---|---|---|
| `Meng Report/ireland datacenter screening data.pdf` | 00386BD086E2517F87CD7B6998A7D1FDCBF4F9A1B234FDE050CB544C7A18978C | Retained as the single active screening copy |
| `Meng Report/ireland_datacentre_rag_english_v1_0.zip :: sources/user_provided_ireland_data_centre_screening_matrix.pdf` | 00386BD086E2517F87CD7B6998A7D1FDCBF4F9A1B234FDE050CB544C7A18978C | DUPLICATE_SKIPPED; remains in the archived original package |
| `Regulations-20260907T183130Z-1-001.zip :: leap-large-energy-user-action-plan (1).pdf` | 0673B3AB0A49FAEACE0AB8432DD1D64082F69B04A0CB236FD4A0B8A13098C6A9 | Identical to the retained standalone LEAP PDF; archive-only |

No destination filename conflicts were found, so no suffix-renamed copies were needed.

## Archive-only contents

The CRU package contained 39 PDFs. Twelve requested files were copied to active folders; these 27 remaining submissions were deliberately left archive-only:

`CRU202504aa - ESI.pdf`, `CRU202504ab - Eastmont developments.pdf`, `CRU202504ad - Fingleton White.pdf`, `CRU202504ae - Finsbury Infrastructure.pdf`, `CRU202504af - Found Digital DS.pdf`, `CRU202504ag - Herbata.pdf`, `CRU202504ak - Kildare Innovation Campus.pdf`, `CRU202504al - Mayo Energy Group.pdf`, `CRU202504am - Orsted.pdf`, `CRU202504ao - Walton Institute.pdf`, `CRU202504b - BGE.pdf`, `CRU202504c - BnaM.pdf`, `CRU202504d - CMI.pdf`, `CRU202504e - Chambers Ireland_0.pdf`, `CRU202504f - CLEAR Consulting_0.pdf`, `CRU202504h - CII.pdf`, `CRU202504i - Codema.pdf`, `CRU202504j - CSC Commodities.pdf`, `CRU202504n - DRAI_1.pdf`, `CRU202504o - EDF Renewables_1.pdf`, `CRU202504p - eHeat_1.pdf`, `CRU202504q - EAI_1.pdf`, `CRU202504s - EngineNode.pdf`, `CRU202504u - EnergyTag_1.pdf`, `CRU202504w - ESB CS_1.pdf`, `CRU202504x - EP UK_1.pdf`, and `CRU202504y - ESB G&T_1.pdf`.

The Regulations package also retains its two duplicate HTML versions and the duplicate LEAP PDF archive-only. The nested Meng package's README remains archive-only; its duplicate screening PDF remains inside the archived original package.

## Inspection and scope notes

- Six top-level source files were inspected: three standalone PDFs and three ZIP packages.
- Three ZIP packages were inspected, including one nested ZIP inside the Meng package.
- ZIP contents inspected: 39 CRU files, 8 Regulations files, 3 outer Meng entries, and 11 nested Meng files.
- No expected requested primary, supporting, governance, restricted, or curated file was missing.
- No current final CRU policy was found; only the proposed/historical decision was present, so `primary/ireland/cru/current/` remains empty.
- Existing official EirGrid and Uisce Éireann files under `data/raw/` were not duplicated.
- Other CRU responses were not automatically classified because the request explicitly limited active extraction to representative public-body and industry submissions; they remain in the archived source ZIP.
- The source folder `D:\Programming\Tech Ireland 2026\RAG` was read-only during this task. No source file was deleted, renamed, moved, overwritten, or modified.
- No RAG/AI/indexing functionality was implemented, and no Module 4B or Module 5 code was changed.
