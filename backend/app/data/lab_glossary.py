"""Curated lab-test glossary (ROADMAP.md Phase 4, memory.md D33).

One entry per test: the canonical name and the aliases labs print, what it measures, GENERAL
reasons it can read high or low (never "yours is high because"), typical units, and a
MedlinePlus page. The explainer quotes this text; it never interprets beyond it.

The key is the slug the trend series uses (`lab_<key>`), so names map to one series:
"LDL-C", "LDL Cholesterol (Direct)" and "LDL" all trend as `lab_ldl_cholesterol`.
"""

import re

_ML = "https://medlineplus.gov/lab-tests/"

GLOSSARY: dict[str, dict] = {
    # --- Diabetes ---------------------------------------------------------------------------
    "hba1c": {
        "name": "HbA1c", "panel": "Diabetes",
        "aliases": ["hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin", "glycated haemoglobin",
                    "glycosylated hemoglobin", "glycosylated haemoglobin", "a1c", "hba1c"],
        "measures": "The average blood sugar over roughly the past 2 to 3 months, as the share of "
                    "haemoglobin that has sugar attached.",
        "high": ["blood sugar running higher than usual over recent months", "some types of anaemia "
                 "or recent blood loss/transfusion can shift the number"],
        "low": ["blood sugar running lower over recent months", "conditions that shorten red blood "
                "cell life can make it read lower"],
        "units": ["%", "mmol/mol"], "url": _ML + "hemoglobin-a1c-hba1c-test/",
    },
    "fasting_glucose": {
        "name": "Fasting glucose", "panel": "Diabetes",
        "aliases": ["fasting plasma glucose", "fasting blood glucose", "fasting blood sugar", "fbs", "fbg",
                    "fpg", "glucose fasting", "blood sugar fasting", "plasma glucose fasting"],
        "measures": "The sugar level in the blood after not eating for at least 8 hours.",
        "high": ["eating shortly before the test", "stress or illness", "some medicines such as steroids",
                 "blood sugar regulation running high"],
        "low": ["a long fast", "diabetes medicines (especially sulfonylureas or insulin)", "alcohol"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "blood-glucose-test/",
    },
    "postprandial_glucose": {
        "name": "Post-meal glucose", "panel": "Diabetes",
        "aliases": ["post prandial glucose", "postprandial glucose", "ppbs", "ppbg", "pp glucose",
                    "post prandial blood sugar", "glucose post prandial", "2 hour glucose",
                    "plasma glucose post prandial"],
        "measures": "The sugar level in the blood about 2 hours after a meal.",
        "high": ["a large or carbohydrate-heavy meal", "blood sugar regulation running high", "stress or illness"],
        "low": ["a small meal", "diabetes medicines"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "blood-glucose-test/",
    },
    "random_glucose": {
        "name": "Random glucose", "panel": "Diabetes",
        "aliases": ["random blood sugar", "rbs", "random plasma glucose", "glucose random", "blood glucose"],
        "measures": "The sugar level in the blood at any time of day, regardless of meals.",
        "high": ["a recent meal", "stress or illness", "blood sugar regulation running high"],
        "low": ["a long gap since eating", "diabetes medicines", "alcohol"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "blood-glucose-test/",
    },
    "estimated_average_glucose": {
        "name": "Estimated average glucose", "panel": "Diabetes",
        "aliases": ["eag", "estimated average glucose", "mean blood glucose", "mean plasma glucose"],
        "measures": "HbA1c converted into an average blood sugar number (calculated, not measured).",
        "high": ["moves with HbA1c"], "low": ["moves with HbA1c"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "hemoglobin-a1c-hba1c-test/",
    },
    # --- Lipids -----------------------------------------------------------------------------
    "total_cholesterol": {
        "name": "Total cholesterol", "panel": "Lipids",
        "aliases": ["cholesterol", "serum cholesterol", "cholesterol total", "total cholesterol"],
        "measures": "All the cholesterol carried in the blood (LDL, HDL and other parts together).",
        "high": ["diet high in saturated fat", "family history", "low physical activity",
                 "an underactive thyroid", "some medicines"],
        "low": ["an overactive thyroid", "poor nutrition", "cholesterol-lowering medicines"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "cholesterol-levels/",
    },
    "ldl_cholesterol": {
        "name": "LDL cholesterol", "panel": "Lipids",
        "aliases": ["ldl", "ldl c", "ldl-c", "ldl cholesterol", "ldl cholesterol direct", "direct ldl",
                    "low density lipoprotein", "ldl calculated", "ldl cholesterol calculated"],
        "measures": "\"Bad\" cholesterol: the kind that can build up in artery walls.",
        "high": ["diet high in saturated or trans fat", "family history", "low physical activity",
                 "excess weight", "an underactive thyroid"],
        "low": ["cholesterol-lowering medicines", "an overactive thyroid", "poor nutrition"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "cholesterol-levels/",
    },
    "hdl_cholesterol": {
        "name": "HDL cholesterol", "panel": "Lipids",
        "aliases": ["hdl", "hdl c", "hdl-c", "hdl cholesterol", "high density lipoprotein", "hdl direct"],
        "measures": "\"Good\" cholesterol: the kind that carries cholesterol away to the liver.",
        "high": ["regular exercise", "genetics"],
        "low": ["smoking", "low physical activity", "excess weight", "high triglycerides"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "cholesterol-levels/",
    },
    "triglycerides": {
        "name": "Triglycerides", "panel": "Lipids",
        "aliases": ["triglyceride", "tg", "serum triglycerides", "trigs"],
        "measures": "A type of fat in the blood that stores unused energy from food.",
        "high": ["a recent meal (not fasting)", "alcohol", "sugary or refined-carb diet",
                 "high blood sugar", "excess weight"],
        "low": ["a low-fat diet", "an overactive thyroid", "some medicines"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "triglycerides-test/",
    },
    "vldl_cholesterol": {
        "name": "VLDL cholesterol", "panel": "Lipids",
        "aliases": ["vldl", "vldl c", "vldl cholesterol", "very low density lipoprotein"],
        "measures": "Cholesterol carried on very-low-density particles; usually calculated from triglycerides.",
        "high": ["moves with triglycerides"], "low": ["moves with triglycerides"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "cholesterol-levels/",
    },
    # --- Blood count ------------------------------------------------------------------------
    "hemoglobin": {
        "name": "Haemoglobin", "panel": "Blood count",
        "aliases": ["hemoglobin", "haemoglobin", "hb", "hgb"],
        "measures": "The protein in red blood cells that carries oxygen.",
        "high": ["dehydration", "smoking", "living at high altitude", "some lung or heart conditions"],
        "low": ["low iron, B12 or folate", "blood loss (including heavy periods)", "long-term illness"],
        "units": ["g/dL", "g/L"], "url": _ML + "hemoglobin-test/",
    },
    "hematocrit": {
        "name": "Haematocrit (PCV)", "panel": "Blood count",
        "aliases": ["hematocrit", "haematocrit", "hct", "pcv", "packed cell volume"],
        "measures": "The share of the blood's volume made up of red blood cells.",
        "high": ["dehydration", "smoking", "living at high altitude"],
        "low": ["low iron, B12 or folate", "blood loss", "long-term illness"],
        "units": ["%"], "url": _ML + "hematocrit-test/",
    },
    "rbc_count": {
        "name": "Red blood cell count", "panel": "Blood count",
        "aliases": ["rbc", "rbc count", "red blood cells", "red blood cell count", "erythrocyte count",
                    "total rbc count"],
        "measures": "How many red blood cells are in a set volume of blood.",
        "high": ["dehydration", "smoking", "living at high altitude"],
        "low": ["low iron, B12 or folate", "blood loss", "long-term illness"],
        "units": ["million/µL", "10^6/µL"], "url": _ML + "red-blood-cell-rbc-count/",
    },
    "wbc_count": {
        "name": "White blood cell count", "panel": "Blood count",
        "aliases": ["wbc", "wbc count", "tlc", "total leucocyte count", "total leukocyte count",
                    "white blood cells", "total wbc count", "white blood cell count"],
        "measures": "How many infection-fighting white blood cells are in the blood.",
        "high": ["an infection", "inflammation", "stress", "steroid medicines", "smoking"],
        "low": ["some viral infections", "some medicines", "conditions affecting the bone marrow"],
        "units": ["/µL", "10^3/µL", "cells/cumm"], "url": _ML + "white-blood-count-wbc/",
    },
    "platelet_count": {
        "name": "Platelet count", "panel": "Blood count",
        "aliases": ["platelets", "platelet count", "plt", "platelet", "thrombocyte count"],
        "measures": "How many platelets (the cells that help blood clot) are in the blood.",
        "high": ["inflammation", "low iron", "recent infection or surgery"],
        "low": ["some viral infections (for example dengue)", "some medicines", "heavy alcohol use"],
        "units": ["/µL", "10^3/µL", "lakhs/cumm"], "url": _ML + "platelet-tests/",
    },
    "mcv": {
        "name": "MCV", "panel": "Blood count",
        "aliases": ["mcv", "mean corpuscular volume", "mean cell volume"],
        "measures": "The average size of red blood cells.",
        "high": ["low B12 or folate", "alcohol", "some medicines"],
        "low": ["low iron", "some inherited haemoglobin traits (such as thalassaemia trait)"],
        "units": ["fL"], "url": _ML + "complete-blood-count-cbc/",
    },
    "esr": {
        "name": "ESR", "panel": "Inflammation",
        "aliases": ["esr", "erythrocyte sedimentation rate", "sed rate"],
        "measures": "How fast red blood cells settle in a tube; a general, non-specific marker of inflammation.",
        "high": ["infection or inflammation", "anaemia", "pregnancy", "older age"],
        "low": ["rarely meaningful on its own"],
        "units": ["mm/hr"], "url": _ML + "erythrocyte-sedimentation-rate-esr/",
    },
    "crp": {
        "name": "C-reactive protein (CRP)", "panel": "Inflammation",
        "aliases": ["crp", "c reactive protein", "c-reactive protein", "hs crp", "hscrp", "hs-crp",
                    "high sensitivity crp"],
        "measures": "A protein the liver makes more of when there is inflammation in the body.",
        "high": ["infection", "inflammation or injury", "recent surgery", "smoking", "excess weight"],
        "low": ["low is the usual result"],
        "units": ["mg/L", "mg/dL"], "url": _ML + "c-reactive-protein-crp-test/",
    },
    # --- Thyroid ----------------------------------------------------------------------------
    "tsh": {
        "name": "TSH", "panel": "Thyroid",
        "aliases": ["tsh", "thyroid stimulating hormone", "thyrotropin", "ultrasensitive tsh", "tsh ultrasensitive"],
        "measures": "The pituitary hormone that tells the thyroid how hard to work. It moves the "
                    "opposite way to thyroid hormone: higher TSH when the thyroid is underactive.",
        "high": ["an underactive thyroid", "too low a dose of thyroid medicine", "recovery from illness"],
        "low": ["an overactive thyroid", "too high a dose of thyroid medicine", "some medicines such as steroids"],
        "units": ["µIU/mL", "mIU/L"], "url": _ML + "tsh-thyroid-stimulating-hormone-test/",
    },
    "free_t4": {
        "name": "Free T4", "panel": "Thyroid",
        "aliases": ["free t4", "ft4", "free thyroxine", "t4 free"],
        "measures": "The active, unbound form of the main thyroid hormone (thyroxine).",
        "high": ["an overactive thyroid", "too high a dose of thyroid medicine"],
        "low": ["an underactive thyroid", "too low a dose of thyroid medicine"],
        "units": ["ng/dL", "pmol/L"], "url": _ML + "thyroxine-t4-test/",
    },
    "total_t4": {
        "name": "Total T4", "panel": "Thyroid",
        "aliases": ["t4", "total t4", "thyroxine", "total thyroxine", "t4 total"],
        "measures": "All the thyroxine in the blood, bound and free.",
        "high": ["an overactive thyroid", "pregnancy or estrogen (raise binding proteins)"],
        "low": ["an underactive thyroid", "illness", "some medicines"],
        "units": ["µg/dL", "nmol/L"], "url": _ML + "thyroxine-t4-test/",
    },
    "free_t3": {
        "name": "Free T3", "panel": "Thyroid",
        "aliases": ["free t3", "ft3", "free triiodothyronine", "t3 free"],
        "measures": "The active, unbound form of triiodothyronine, the stronger thyroid hormone.",
        "high": ["an overactive thyroid"], "low": ["an underactive thyroid", "illness or fasting"],
        "units": ["pg/mL", "pmol/L"], "url": _ML + "triiodothyronine-t3-tests/",
    },
    "total_t3": {
        "name": "Total T3", "panel": "Thyroid",
        "aliases": ["t3", "total t3", "triiodothyronine", "total triiodothyronine", "t3 total"],
        "measures": "All the triiodothyronine in the blood, bound and free.",
        "high": ["an overactive thyroid", "pregnancy or estrogen"],
        "low": ["an underactive thyroid", "illness or fasting"],
        "units": ["ng/dL", "nmol/L"], "url": _ML + "triiodothyronine-t3-tests/",
    },
    # --- Kidney -----------------------------------------------------------------------------
    "creatinine": {
        "name": "Creatinine", "panel": "Kidney",
        "aliases": ["creatinine", "serum creatinine", "s creatinine", "creatinine serum"],
        "measures": "A waste product from muscles that the kidneys filter out; used to judge kidney filtering.",
        "high": ["dehydration", "high muscle mass or a lot of meat just before the test",
                 "reduced kidney filtering", "some medicines"],
        "low": ["low muscle mass", "pregnancy"],
        "units": ["mg/dL", "µmol/L"], "url": _ML + "creatinine-test/",
    },
    "egfr": {
        "name": "eGFR", "panel": "Kidney",
        "aliases": ["egfr", "estimated gfr", "estimated glomerular filtration rate", "gfr"],
        "measures": "An estimate of how much blood the kidneys filter each minute, calculated from "
                    "creatinine, age and sex.",
        "high": ["higher is usually the expected direction"],
        "low": ["reduced kidney filtering", "dehydration", "older age"],
        "units": ["mL/min/1.73m²"], "url": _ML + "glomerular-filtration-rate-gfr-test/",
    },
    "urea": {
        "name": "Urea", "panel": "Kidney",
        "aliases": ["urea", "blood urea", "serum urea", "urea serum"],
        "measures": "A waste product from breaking down protein, filtered out by the kidneys.",
        "high": ["dehydration", "a high-protein diet", "reduced kidney filtering", "some medicines"],
        "low": ["a low-protein diet", "liver conditions", "overhydration"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "bun-blood-urea-nitrogen/",
    },
    "bun": {
        "name": "Blood urea nitrogen (BUN)", "panel": "Kidney",
        "aliases": ["bun", "blood urea nitrogen", "urea nitrogen"],
        "measures": "The nitrogen part of urea; another way of reporting urea.",
        "high": ["dehydration", "a high-protein diet", "reduced kidney filtering"],
        "low": ["a low-protein diet", "liver conditions"],
        "units": ["mg/dL"], "url": _ML + "bun-blood-urea-nitrogen/",
    },
    "uric_acid": {
        "name": "Uric acid", "panel": "Kidney",
        "aliases": ["uric acid", "serum uric acid", "s uric acid"],
        "measures": "A waste product from breaking down purines (found in some foods and in the body's cells).",
        "high": ["purine-rich food (red meat, seafood)", "alcohol, especially beer", "dehydration",
                 "some medicines such as water pills", "reduced kidney filtering"],
        "low": ["some medicines", "a low-purine diet"],
        "units": ["mg/dL", "µmol/L"], "url": _ML + "uric-acid-test/",
    },
    "sodium": {
        "name": "Sodium", "panel": "Electrolytes",
        "aliases": ["sodium", "na", "serum sodium", "na+", "s sodium"],
        "measures": "A salt in the blood that helps control fluid balance, nerves and muscles.",
        "high": ["dehydration", "not drinking enough", "some medicines"],
        "low": ["drinking a lot of water", "vomiting or diarrhoea", "water pills and some other medicines"],
        "units": ["mmol/L", "mEq/L"], "url": _ML + "sodium-blood-test/",
    },
    "potassium": {
        "name": "Potassium", "panel": "Electrolytes",
        "aliases": ["potassium", "k", "serum potassium", "k+", "s potassium"],
        "measures": "A mineral that keeps nerves, muscles and the heart rhythm working normally.",
        "high": ["some blood pressure medicines", "reduced kidney filtering",
                 "a sample that was damaged on the way to the lab"],
        "low": ["vomiting or diarrhoea", "water pills", "some other medicines"],
        "units": ["mmol/L", "mEq/L"], "url": _ML + "potassium-blood-test/",
    },
    "chloride": {
        "name": "Chloride", "panel": "Electrolytes",
        "aliases": ["chloride", "cl", "serum chloride", "cl-"],
        "measures": "A salt in the blood that works with sodium to keep fluid and acid balance.",
        "high": ["dehydration", "some medicines"], "low": ["vomiting", "water pills"],
        "units": ["mmol/L", "mEq/L"], "url": _ML + "chloride-blood-test/",
    },
    "calcium": {
        "name": "Calcium", "panel": "Minerals",
        "aliases": ["calcium", "serum calcium", "total calcium", "ca"],
        "measures": "The mineral for bones, teeth, muscles and nerves.",
        "high": ["overactive parathyroid glands", "too much calcium or vitamin D supplement", "some medicines"],
        "low": ["low vitamin D", "low albumin (calcium is carried on it)", "low magnesium"],
        "units": ["mg/dL", "mmol/L"], "url": _ML + "calcium-blood-test/",
    },
    # --- Liver ------------------------------------------------------------------------------
    "alt": {
        "name": "ALT (SGPT)", "panel": "Liver",
        "aliases": ["alt", "sgpt", "alanine aminotransferase", "alanine transaminase", "alt sgpt", "sgpt alt"],
        "measures": "A liver enzyme that leaks into the blood when liver cells are irritated.",
        "high": ["fatty liver", "alcohol", "some medicines (including some pain relievers)",
                 "a viral infection", "heavy exercise"],
        "low": ["low is the usual result"],
        "units": ["U/L", "IU/L"], "url": _ML + "alt-blood-test/",
    },
    "ast": {
        "name": "AST (SGOT)", "panel": "Liver",
        "aliases": ["ast", "sgot", "aspartate aminotransferase", "aspartate transaminase", "ast sgot", "sgot ast"],
        "measures": "An enzyme found in the liver and muscles; rises when either is irritated.",
        "high": ["alcohol", "fatty liver", "some medicines", "muscle injury or heavy exercise"],
        "low": ["low is the usual result"],
        "units": ["U/L", "IU/L"], "url": _ML + "ast-test/",
    },
    "alkaline_phosphatase": {
        "name": "Alkaline phosphatase (ALP)", "panel": "Liver",
        "aliases": ["alkaline phosphatase", "alp", "alk phos", "serum alkaline phosphatase"],
        "measures": "An enzyme from the liver, bile ducts and bones.",
        "high": ["blocked bile flow", "bone growth or healing", "pregnancy", "some medicines"],
        "low": ["poor nutrition", "low zinc or magnesium"],
        "units": ["U/L", "IU/L"], "url": _ML + "alkaline-phosphatase/",
    },
    "total_bilirubin": {
        "name": "Total bilirubin", "panel": "Liver",
        "aliases": ["bilirubin", "total bilirubin", "bilirubin total", "serum bilirubin", "t bilirubin"],
        "measures": "A yellow pigment from the normal breakdown of red blood cells, cleared by the liver.",
        "high": ["Gilbert's syndrome (a common, usually harmless trait)", "fasting",
                 "faster red cell breakdown", "liver or bile duct problems"],
        "low": ["low is the usual result"],
        "units": ["mg/dL", "µmol/L"], "url": _ML + "bilirubin-blood-test/",
    },
    "direct_bilirubin": {
        "name": "Direct bilirubin", "panel": "Liver",
        "aliases": ["direct bilirubin", "conjugated bilirubin", "bilirubin direct"],
        "measures": "The part of bilirubin the liver has already processed.",
        "high": ["blocked bile flow", "liver problems"], "low": ["low is the usual result"],
        "units": ["mg/dL", "µmol/L"], "url": _ML + "bilirubin-blood-test/",
    },
    "albumin": {
        "name": "Albumin", "panel": "Liver",
        "aliases": ["albumin", "serum albumin", "s albumin"],
        "measures": "The main protein made by the liver; it holds fluid in the blood vessels.",
        "high": ["dehydration"],
        "low": ["poor nutrition", "long-term illness or inflammation", "liver or kidney problems"],
        "units": ["g/dL", "g/L"], "url": _ML + "albumin-blood-test/",
    },
    "total_protein": {
        "name": "Total protein", "panel": "Liver",
        "aliases": ["total protein", "serum protein", "protein total", "total proteins"],
        "measures": "Albumin plus globulins (proteins that include antibodies).",
        "high": ["dehydration", "long-term inflammation or infection"],
        "low": ["poor nutrition", "liver or kidney problems"],
        "units": ["g/dL", "g/L"], "url": _ML + "total-protein-and-albumin-globulin-a-g-ratio/",
    },
    "ggt": {
        "name": "GGT", "panel": "Liver",
        "aliases": ["ggt", "gamma gt", "gamma glutamyl transferase", "gamma glutamyltransferase", "ggtp"],
        "measures": "A liver and bile-duct enzyme, sensitive to alcohol and some medicines.",
        "high": ["alcohol", "some medicines", "fatty liver", "blocked bile flow"],
        "low": ["low is the usual result"],
        "units": ["U/L", "IU/L"], "url": _ML + "gamma-glutamyl-transferase-ggt-test/",
    },
    # --- Vitamins and iron ------------------------------------------------------------------
    "vitamin_d": {
        "name": "Vitamin D (25-OH)", "panel": "Vitamins",
        "aliases": ["vitamin d", "25 oh vitamin d", "25-oh vitamin d", "25 hydroxy vitamin d",
                    "vitamin d3", "vitamin d total", "25 hydroxyvitamin d", "vit d"],
        "measures": "The body's store of vitamin D, needed for calcium and bone health.",
        "high": ["high-dose supplements"],
        "low": ["little sun exposure", "darker skin", "a diet low in vitamin D", "excess weight",
                "some gut or kidney problems"],
        "units": ["ng/mL", "nmol/L"], "url": _ML + "vitamin-d-test/",
    },
    "vitamin_b12": {
        "name": "Vitamin B12", "panel": "Vitamins",
        "aliases": ["vitamin b12", "b12", "cobalamin", "cyanocobalamin", "vit b12"],
        "measures": "The level of vitamin B12, needed for nerves and making red blood cells.",
        "high": ["supplements or injections"],
        "low": ["a vegetarian or vegan diet", "long-term metformin or acid-reducing medicines",
                "poor absorption from the gut", "older age"],
        "units": ["pg/mL", "pmol/L"], "url": _ML + "vitamin-b-test/",
    },
    "ferritin": {
        "name": "Ferritin", "panel": "Iron",
        "aliases": ["ferritin", "serum ferritin"],
        "measures": "The protein that stores iron; shows how much iron the body has in reserve.",
        "high": ["inflammation or infection", "liver problems", "iron overload"],
        "low": ["low iron stores", "blood loss (including heavy periods)", "a low-iron diet"],
        "units": ["ng/mL", "µg/L"], "url": _ML + "ferritin-blood-test/",
    },
    "iron": {
        "name": "Serum iron", "panel": "Iron",
        "aliases": ["iron", "serum iron", "s iron"],
        "measures": "The iron circulating in the blood at the time of the test (it varies through the day).",
        "high": ["iron supplements", "iron overload"],
        "low": ["low iron stores", "blood loss", "inflammation"],
        "units": ["µg/dL", "µmol/L"], "url": _ML + "iron-tests/",
    },
    # --- Urine ------------------------------------------------------------------------------
    "urine_protein": {
        "name": "Urine protein", "panel": "Urine",
        "aliases": ["urine protein", "protein urine", "urine albumin", "albumin urine", "proteinuria"],
        "measures": "Whether protein is passing into the urine (normally almost none does).",
        "high": ["heavy exercise", "fever or illness", "dehydration", "kidney filtering problems"],
        "low": ["none or trace is the usual result"],
        "units": ["mg/dL", "nil/trace/+"], "url": _ML + "protein-in-urine/",
    },
    "urine_glucose": {
        "name": "Urine glucose", "panel": "Urine",
        "aliases": ["urine glucose", "urine sugar", "glucose urine", "sugar urine"],
        "measures": "Whether sugar is spilling into the urine (usually when blood sugar is high).",
        "high": ["high blood sugar", "some diabetes medicines (SGLT2 inhibitors) cause it by design",
                 "pregnancy"],
        "low": ["none is the usual result"],
        "units": ["nil/trace/+", "mg/dL"], "url": _ML + "glucose-in-urine-test/",
    },
    "urine_ketones": {
        "name": "Urine ketones", "panel": "Urine",
        "aliases": ["urine ketones", "ketones", "ketone bodies", "ketones urine", "acetone"],
        "measures": "Whether the body is burning fat for fuel instead of sugar.",
        "high": ["fasting or a very low-carb diet", "vomiting", "very high blood sugar"],
        "low": ["none is the usual result"],
        "units": ["nil/trace/+"], "url": _ML + "ketones-in-urine/",
    },
    "urine_pus_cells": {
        "name": "Urine pus cells (WBC)", "panel": "Urine",
        "aliases": ["pus cells", "urine pus cells", "urine wbc", "leukocytes urine", "wbc urine",
                    "pus cells urine"],
        "measures": "White blood cells in the urine.",
        "high": ["a urinary infection", "inflammation in the urinary tract", "a contaminated sample"],
        "low": ["a few or none is the usual result"],
        "units": ["/hpf"], "url": "https://medlineplus.gov/urinalysis.html",
    },
    "urine_acr": {
        "name": "Urine albumin/creatinine ratio", "panel": "Urine",
        "aliases": ["uacr", "acr", "albumin creatinine ratio", "urine albumin creatinine ratio",
                    "microalbumin", "urine microalbumin", "microalbumin creatinine ratio"],
        "measures": "Small amounts of albumin in the urine, compared with creatinine; an early "
                    "check on kidney filtering, often done yearly with diabetes.",
        "high": ["heavy exercise", "fever", "high blood sugar or blood pressure over time",
                 "kidney filtering problems"],
        "low": ["low is the usual result"],
        "units": ["mg/g", "mg/mmol"], "url": _ML + "microalbumin-creatinine-ratio/",
    },
}


def normalize(name: str | None) -> str:
    """Lowercase, symbols to spaces, collapse: 'LDL-C' -> 'ldl c'."""
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", (name or "").lower()).split())


def _build_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for key, entry in GLOSSARY.items():
        for alias in [key.replace("_", " "), entry["name"], *entry["aliases"]]:
            index.setdefault(normalize(alias), key)
    return index


_INDEX = _build_index()


def key_for(name: str | None) -> str | None:
    """The glossary key for a printed test name, or None if it isn't a known test.

    Tries the whole name, then without parentheses ('LDL Cholesterol (Direct)'), then each
    part of a 'A / B' or 'A - B' name ('SGPT / ALT')."""
    if not name:
        return None
    candidates = [name, re.sub(r"\(.*?\)", " ", name), *re.findall(r"\(([^)]*)\)", name)]
    candidates += [p for c in list(candidates) for p in re.split(r"\s[/-]\s|/", c)]
    for c in candidates:
        key = _INDEX.get(normalize(c))
        if key:
            return key
    return None


def lookup(name: str | None) -> dict | None:
    key = key_for(name)
    return {"key": key, **GLOSSARY[key]} if key else None


def mentioned(text: str) -> list[str]:
    """Glossary keys whose name or alias appears as whole words in free text ('what is TSH?').
    One- and two-letter aliases ('k', 'na', 'ca') are skipped: too easy to hit by accident."""
    t = f" {normalize(text)} "
    found: list[str] = []
    for alias, key in _INDEX.items():
        if (len(alias) < 3 and alias != "hb") or key in found:
            continue
        if f" {alias} " in t:
            found.append(key)
    return found
