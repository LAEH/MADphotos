"""Signal inspector, embedding audit, collection coverage, and schema data generators."""
from __future__ import annotations

import json
import sqlite3

from ._common import DB_PATH, PROJECT_ROOT, human_bytes
from .vectors import _get_lance


def generate_signal_inspector_data():
    """Generate signal inspector data: 300 stratified images with all signals."""
    import random
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]

    # Get aesthetic quartile boundaries
    scores = [r[0] for r in conn.execute(
        "SELECT score FROM aesthetic_scores ORDER BY score"
    ).fetchall()]
    if scores:
        q1 = scores[len(scores)//4]
        q2 = scores[len(scores)//2]
        q3 = scores[3*len(scores)//4]
    else:
        q1, q2, q3 = 4, 6, 8

    # Get camera distribution
    cameras = conn.execute(
        "SELECT camera_body, COUNT(*) as cnt FROM images GROUP BY camera_body ORDER BY cnt DESC"
    ).fetchall()
    camera_counts = {r["camera_body"]: r["cnt"] for r in cameras}
    total_imgs = sum(camera_counts.values())

    # Sample 300 images: proportional by camera, even by quartile
    sample_uuids = set()
    target = 300
    per_quartile = target // 4

    for q_idx, (lo, hi) in enumerate([(0, q1), (q1, q2), (q2, q3), (q3, 11)]):
        # Get images in this quartile
        uuids_in_q = [r[0] for r in conn.execute("""
            SELECT i.uuid FROM images i
            JOIN aesthetic_scores a ON i.uuid = a.image_uuid
            WHERE a.score >= ? AND a.score < ?
        """, (lo, hi)).fetchall()]
        random.shuffle(uuids_in_q)
        # Take proportional per camera within this quartile
        needed = per_quartile
        for uuid in uuids_in_q:
            if len(sample_uuids) >= target:
                break
            sample_uuids.add(uuid)
            needed -= 1
            if needed <= 0:
                break

    # Fill remainder randomly if needed
    if len(sample_uuids) < target:
        all_uuids = [r[0] for r in conn.execute("SELECT uuid FROM images").fetchall()]
        random.shuffle(all_uuids)
        for u in all_uuids:
            if u not in sample_uuids:
                sample_uuids.add(u)
            if len(sample_uuids) >= target:
                break

    # Build full signal records
    images = []
    for uuid in sample_uuids:
        img = conn.execute("SELECT uuid, category, subcategory, camera_body, width, height FROM images WHERE uuid=?", (uuid,)).fetchone()
        if not img:
            continue

        rec = {
            "uuid": img["uuid"],
            "thumb": f"/rendered/thumb/jpeg/{img['uuid']}.jpg",
            "display": f"/rendered/display/jpeg/{img['uuid']}.jpg",
            "camera": img["camera_body"],
            "w": img["width"] or 0,
            "h": img["height"] or 0,
        }

        # Gemini analysis
        g = conn.execute("SELECT * FROM gemini_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        if g:
            rec["caption"] = g["alt_text"] or ""
            rec["alt"] = g["alt_text"] or ""
            rec["style"] = g["grading_style"] or ""
            rec["grading"] = g["grading_style"] or ""
            rec["time"] = g["time_of_day"] or ""
            rec["setting"] = g["setting"] or ""
            rec["exposure"] = g["exposure"] or ""
            rec["composition"] = g["composition_technique"] or ""
            rec["weather"] = g["weather"] or ""
            rec["sharpness"] = g["sharpness"] or ""
            try:
                rec["vibes"] = json.loads(g["vibe"]) if g["vibe"] else []
            except:
                rec["vibes"] = []
        else:
            rec.update({"caption": "", "alt": "", "style": "", "grading": "",
                       "time": "", "setting": "", "exposure": "", "composition": "",
                       "weather": "", "sharpness": "",
                       "vibes": []})

        # Scene classification
        sc_row = conn.execute("SELECT scene_1, environment FROM scene_classification WHERE image_uuid=?", (uuid,)).fetchone()
        if sc_row:
            rec["scene"] = sc_row["scene_1"] or ""
            rec["environment"] = sc_row["environment"] or ""
        else:
            rec["scene"] = ""
            rec["environment"] = ""

        # Style classification
        sc = conn.execute("SELECT style FROM style_classification WHERE image_uuid=?", (uuid,)).fetchone()
        if sc:
            rec["style"] = sc["style"] or rec.get("style", "")

        # Aesthetic score
        ae = conn.execute("SELECT score FROM aesthetic_scores WHERE image_uuid=?", (uuid,)).fetchone()
        rec["aesthetic"] = round(float(ae["score"]), 1) if ae else 0

        # Dominant colors (top 5)
        colors = conn.execute(
            "SELECT hex, percentage, color_name FROM dominant_colors WHERE image_uuid=? ORDER BY percentage DESC LIMIT 5",
            (uuid,)
        ).fetchall()
        rec["colors"] = [{"hex": c["hex"] or "#000", "pct": round(float(c["percentage"] or 0), 1), "name": c["color_name"] or ""} for c in colors]

        # Depth
        de = conn.execute("SELECT near_pct, mid_pct, far_pct FROM depth_estimation WHERE image_uuid=?", (uuid,)).fetchone()
        if de:
            rec["depth"] = {"near": round(float(de["near_pct"] or 0), 1), "mid": round(float(de["mid_pct"] or 0), 1), "far": round(float(de["far_pct"] or 0), 1)}
        else:
            rec["depth"] = {"near": 0, "mid": 0, "far": 0}

        # Objects
        objs = conn.execute(
            "SELECT label, confidence FROM object_detections WHERE image_uuid=? ORDER BY confidence DESC LIMIT 10",
            (uuid,)
        ).fetchall()
        rec["objects"] = [{"label": o["label"], "conf": round(float(o["confidence"] or 0), 2)} for o in objs]

        # Faces
        faces = conn.execute(
            "SELECT confidence, face_area_pct FROM face_detections WHERE image_uuid=?",
            (uuid,)
        ).fetchall()
        face_list = []
        for f in faces:
            fe = conn.execute("SELECT dominant_emotion FROM facial_emotions WHERE image_uuid=?", (uuid,)).fetchone()
            face_list.append({
                "conf": round(float(f["confidence"] or 0), 2),
                "area": round(float(f["face_area_pct"] or 0), 3),
                "emotion": fe["dominant_emotion"] if fe else ""
            })
        rec["faces"] = face_list

        # OCR
        ocr = conn.execute(
            "SELECT text FROM ocr_detections WHERE image_uuid=? AND text != ''",
            (uuid,)
        ).fetchall()
        rec["ocr"] = [o["text"] for o in ocr]

        # EXIF
        ex = conn.execute("SELECT focal_length, aperture, shutter_speed, iso, make, model, lens, date_taken FROM exif_metadata WHERE image_uuid=?", (uuid,)).fetchone()
        if ex:
            rec["exif"] = {
                "focal": ex["focal_length"] or 0,
                "aperture": ex["aperture"] or 0,
                "shutter": ex["shutter_speed"] or "",
                "iso": ex["iso"] or 0,
                "make": ex["make"] or "",
                "model": ex["model"] or "",
                "lens": ex["lens"] or "",
                "date": ex["date_taken"] or "",
            }
        else:
            rec["exif"] = {"focal": 0, "aperture": 0, "shutter": "", "iso": 0}

        # Caption from BLIP
        cap = conn.execute("SELECT caption FROM image_captions WHERE image_uuid=?", (uuid,)).fetchone()
        if cap and cap["caption"]:
            rec["blip_caption"] = cap["caption"]

        # aesthetic_scores_v2
        av2 = conn.execute("SELECT topiq_score, musiq_score, laion_score, composite_score FROM aesthetic_scores_v2 WHERE image_uuid=?", (uuid,)).fetchone()
        if av2:
            rec["aesthetic_v2"] = {"topiq": round(float(av2["topiq_score"] or 0), 2), "musiq": round(float(av2["musiq_score"] or 0), 2), "laion": round(float(av2["laion_score"] or 0), 2), "composite": round(float(av2["composite_score"] or 0), 2)}

        # quality_scores
        qs = conn.execute("SELECT technical_score, clip_score, combined_score, sharpness, noise, exposure_quality, contrast FROM quality_scores WHERE image_uuid=?", (uuid,)).fetchone()
        if qs:
            rec["quality"] = {"technical": round(float(qs["technical_score"] or 0), 2), "clip": round(float(qs["clip_score"] or 0), 2), "combined": round(float(qs["combined_score"] or 0), 2)}

        # florence_captions
        fc = conn.execute("SELECT short_caption, detailed_caption FROM florence_captions WHERE image_uuid=?", (uuid,)).fetchone()
        if fc:
            rec["florence"] = {"short": fc["short_caption"] or "", "detailed": fc["detailed_caption"] or ""}

        # image_tags (pipe-delimited)
        tg = conn.execute("SELECT tags, tag_count FROM image_tags WHERE image_uuid=?", (uuid,)).fetchone()
        if tg and tg["tags"]:
            rec["tags"] = [t.strip() for t in tg["tags"].split("|")][:8]

        # open_detections (Grounding DINO)
        od = conn.execute("SELECT label, confidence FROM open_detections WHERE image_uuid=? ORDER BY confidence DESC LIMIT 8", (uuid,)).fetchall()
        rec["open_objects"] = [{"label": o["label"], "conf": round(float(o["confidence"] or 0), 2)} for o in od]

        # face_identities
        fi = conn.execute("SELECT DISTINCT identity_label FROM face_identities WHERE image_uuid=? AND identity_label IS NOT NULL", (uuid,)).fetchall()
        rec["identities"] = [f["identity_label"] for f in fi]

        # foreground_masks
        fg = conn.execute("SELECT foreground_pct, background_pct FROM foreground_masks WHERE image_uuid=?", (uuid,)).fetchone()
        if fg:
            rec["foreground"] = {"fg_pct": round(float(fg["foreground_pct"] or 0), 1), "bg_pct": round(float(fg["background_pct"] or 0), 1)}

        # segmentation_masks
        sg = conn.execute("SELECT segment_count, largest_segment_pct FROM segmentation_masks WHERE image_uuid=?", (uuid,)).fetchone()
        if sg:
            rec["segments"] = {"count": sg["segment_count"] or 0, "largest_pct": round(float(sg["largest_segment_pct"] or 0), 1)}

        # pose_detections
        pd_rows = conn.execute("SELECT pose_score FROM pose_detections WHERE image_uuid=?", (uuid,)).fetchall()
        rec["poses"] = len(pd_rows)

        # saliency_maps
        sal = conn.execute("SELECT peak_x, peak_y, spread, center_bias FROM saliency_maps WHERE image_uuid=?", (uuid,)).fetchone()
        if sal:
            rec["saliency"] = {"peak_x": round(float(sal["peak_x"] or 0), 2), "peak_y": round(float(sal["peak_y"] or 0), 2), "spread": round(float(sal["spread"] or 0), 2), "center_bias": round(float(sal["center_bias"] or 0), 2)}

        # image_locations
        loc = conn.execute("SELECT location_name, latitude, longitude FROM image_locations WHERE image_uuid=?", (uuid,)).fetchone()
        if loc:
            rec["location"] = {"name": loc["location_name"] or "", "lat": loc["latitude"], "lon": loc["longitude"]}

        # image_hashes
        ih = conn.execute("SELECT blur_score, sharpness_score, edge_density, entropy FROM image_hashes WHERE image_uuid=?", (uuid,)).fetchone()
        if ih:
            rec["hashes"] = {"blur": round(float(ih["blur_score"] or 0), 1), "sharpness": round(float(ih["sharpness_score"] or 0), 1), "edge_density": round(float(ih["edge_density"] or 0), 3), "entropy": round(float(ih["entropy"] or 0), 2)}

        # image_analysis
        ia = conn.execute("SELECT mean_brightness, dynamic_range, noise_estimate, est_color_temp FROM image_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        if ia:
            rec["analysis"] = {"brightness": round(float(ia["mean_brightness"] or 0), 1), "dynamic_range": round(float(ia["dynamic_range"] or 0), 1), "noise": round(float(ia["noise_estimate"] or 0), 2), "color_temp": int(ia["est_color_temp"] or 0)}

        # border_crops
        bc = conn.execute("SELECT has_border, border_pct FROM border_crops WHERE image_uuid=?", (uuid,)).fetchone()
        if bc and bc["has_border"]:
            rec["border"] = round(float(bc["border_pct"] or 0), 1)

        images.append(rec)

    conn.close()
    return {
        "sample_size": len(images),
        "total": total,
        "images": images,
    }


def get_signal_inspector_picks_data():
    """Return all DB signals for ~100 random picked images."""
    import random
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Load picks UUIDs
    picks_json = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"
    try:
        picks = json.loads(picks_json.read_text())
        all_uuids = list(set(picks.get("portrait", []) + picks.get("landscape", [])))
    except Exception:
        all_uuids = []

    total_picks = len(all_uuids)
    random.shuffle(all_uuids)
    sample_uuids = all_uuids[:100]

    images = []
    for uuid in sample_uuids:
        img = conn.execute(
            "SELECT uuid, category, subcategory, camera_body, film_stock, width, height FROM images WHERE uuid=?",
            (uuid,)
        ).fetchone()
        if not img:
            continue

        rec = {
            "uuid": img["uuid"],
            "thumb": f"/rendered/thumb/jpeg/{img['uuid']}.jpg",
            "display": f"/rendered/display/jpeg/{img['uuid']}.jpg",
            "camera": img["camera_body"] or "",
            "film": img["film_stock"] or "",
            "category": img["category"] or "",
            "subcategory": img["subcategory"] or "",
            "w": img["width"] or 0,
            "h": img["height"] or 0,
        }

        # Gemini analysis
        g = conn.execute("SELECT * FROM gemini_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        if g:
            rec["gemini_alt"] = g["alt_text"] or ""
            rec["grading"] = g["grading_style"] or ""
            rec["time"] = g["time_of_day"] or ""
            rec["setting"] = g["setting"] or ""
            rec["exposure"] = g["exposure"] or ""
            rec["composition"] = g["composition_technique"] or ""
            rec["weather"] = g["weather"] or ""
            rec["gemini_sharpness"] = g["sharpness"] or ""
            try:
                rec["vibes"] = json.loads(g["vibe"]) if g["vibe"] else []
            except Exception:
                rec["vibes"] = []

        # Scene classification
        sc_row = conn.execute("SELECT scene_1, environment FROM scene_classification WHERE image_uuid=?", (uuid,)).fetchone()
        if sc_row:
            rec["scene"] = sc_row["scene_1"] or ""
            rec["environment"] = sc_row["environment"] or ""

        # Style classification
        sc = conn.execute("SELECT style FROM style_classification WHERE image_uuid=?", (uuid,)).fetchone()
        if sc:
            rec["style"] = sc["style"] or ""

        # Aesthetic score v1
        ae = conn.execute("SELECT score FROM aesthetic_scores WHERE image_uuid=?", (uuid,)).fetchone()
        rec["aesthetic"] = round(float(ae["score"]), 1) if ae else 0

        # Aesthetic scores v2
        av2 = conn.execute("SELECT topiq_score, musiq_score, laion_score, composite_score FROM aesthetic_scores_v2 WHERE image_uuid=?", (uuid,)).fetchone()
        if av2:
            rec["aesthetic_v2"] = {"topiq": round(float(av2["topiq_score"] or 0), 2), "musiq": round(float(av2["musiq_score"] or 0), 2), "laion": round(float(av2["laion_score"] or 0), 2), "composite": round(float(av2["composite_score"] or 0), 2)}

        # Quality scores
        qs = conn.execute("SELECT technical_score, clip_score, combined_score FROM quality_scores WHERE image_uuid=?", (uuid,)).fetchone()
        if qs:
            rec["quality"] = {"technical": round(float(qs["technical_score"] or 0), 2), "clip": round(float(qs["clip_score"] or 0), 2), "combined": round(float(qs["combined_score"] or 0), 2)}

        # Dominant colors (top 5)
        colors = conn.execute(
            "SELECT hex, percentage, color_name FROM dominant_colors WHERE image_uuid=? ORDER BY percentage DESC LIMIT 5",
            (uuid,)
        ).fetchall()
        rec["colors"] = [{"hex": c["hex"] or "#000", "pct": round(float(c["percentage"] or 0), 1), "name": c["color_name"] or ""} for c in colors]

        # Depth
        de = conn.execute("SELECT near_pct, mid_pct, far_pct FROM depth_estimation WHERE image_uuid=?", (uuid,)).fetchone()
        if de:
            rec["depth"] = {"near": round(float(de["near_pct"] or 0), 1), "mid": round(float(de["mid_pct"] or 0), 1), "far": round(float(de["far_pct"] or 0), 1)}

        # YOLO Objects
        objs = conn.execute(
            "SELECT label, confidence FROM object_detections WHERE image_uuid=? ORDER BY confidence DESC LIMIT 10",
            (uuid,)
        ).fetchall()
        rec["objects"] = [{"label": o["label"], "conf": round(float(o["confidence"] or 0), 2)} for o in objs]

        # Open detections (Grounding DINO)
        od = conn.execute("SELECT label, confidence FROM open_detections WHERE image_uuid=? ORDER BY confidence DESC LIMIT 8", (uuid,)).fetchall()
        rec["open_objects"] = [{"label": o["label"], "conf": round(float(o["confidence"] or 0), 2)} for o in od]

        # Faces + emotions
        faces = conn.execute(
            "SELECT confidence, face_area_pct FROM face_detections WHERE image_uuid=?",
            (uuid,)
        ).fetchall()
        face_list = []
        for f in faces:
            fe = conn.execute("SELECT dominant_emotion FROM facial_emotions WHERE image_uuid=?", (uuid,)).fetchone()
            face_list.append({
                "conf": round(float(f["confidence"] or 0), 2),
                "area": round(float(f["face_area_pct"] or 0), 3),
                "emotion": fe["dominant_emotion"] if fe else ""
            })
        rec["faces"] = face_list

        # Face identities
        fi = conn.execute("SELECT DISTINCT identity_label FROM face_identities WHERE image_uuid=? AND identity_label IS NOT NULL", (uuid,)).fetchall()
        rec["identities"] = [f["identity_label"] for f in fi]

        # OCR
        ocr = conn.execute(
            "SELECT text FROM ocr_detections WHERE image_uuid=? AND text != ''",
            (uuid,)
        ).fetchall()
        rec["ocr"] = [o["text"] for o in ocr]

        # EXIF
        ex = conn.execute("SELECT focal_length, aperture, shutter_speed, iso, make, model, lens, date_taken FROM exif_metadata WHERE image_uuid=?", (uuid,)).fetchone()
        if ex:
            rec["exif"] = {
                "focal": ex["focal_length"] or 0,
                "aperture": ex["aperture"] or 0,
                "shutter": ex["shutter_speed"] or "",
                "iso": ex["iso"] or 0,
                "make": ex["make"] or "",
                "model": ex["model"] or "",
                "lens": ex["lens"] or "",
                "date": ex["date_taken"] or "",
            }

        # BLIP caption
        cap = conn.execute("SELECT caption FROM image_captions WHERE image_uuid=?", (uuid,)).fetchone()
        if cap and cap["caption"]:
            rec["blip_caption"] = cap["caption"]

        # Florence captions
        fc = conn.execute("SELECT short_caption, detailed_caption FROM florence_captions WHERE image_uuid=?", (uuid,)).fetchone()
        if fc:
            rec["florence"] = {"short": fc["short_caption"] or "", "detailed": fc["detailed_caption"] or ""}

        # Image tags (CLIP/RAM)
        tg = conn.execute("SELECT tags, tag_count FROM image_tags WHERE image_uuid=?", (uuid,)).fetchone()
        if tg and tg["tags"]:
            rec["clip_tags"] = [t.strip() for t in tg["tags"].split("|")][:12]

        # Foreground masks
        fg = conn.execute("SELECT foreground_pct, background_pct FROM foreground_masks WHERE image_uuid=?", (uuid,)).fetchone()
        if fg:
            rec["foreground"] = {"fg_pct": round(float(fg["foreground_pct"] or 0), 1), "bg_pct": round(float(fg["background_pct"] or 0), 1)}

        # Segmentation masks
        sg = conn.execute("SELECT segment_count, largest_segment_pct FROM segmentation_masks WHERE image_uuid=?", (uuid,)).fetchone()
        if sg:
            rec["segments"] = {"count": sg["segment_count"] or 0, "largest_pct": round(float(sg["largest_segment_pct"] or 0), 1)}

        # Pose detections
        pd_rows = conn.execute("SELECT pose_score FROM pose_detections WHERE image_uuid=?", (uuid,)).fetchall()
        rec["poses"] = len(pd_rows)

        # Saliency maps
        sal = conn.execute("SELECT peak_x, peak_y, spread, center_bias FROM saliency_maps WHERE image_uuid=?", (uuid,)).fetchone()
        if sal:
            rec["saliency"] = {"peak_x": round(float(sal["peak_x"] or 0), 2), "peak_y": round(float(sal["peak_y"] or 0), 2), "spread": round(float(sal["spread"] or 0), 2), "center_bias": round(float(sal["center_bias"] or 0), 2)}

        # Image location
        loc = conn.execute("SELECT location_name, latitude, longitude FROM image_locations WHERE image_uuid=?", (uuid,)).fetchone()
        if loc:
            rec["location"] = {"name": loc["location_name"] or "", "lat": loc["latitude"], "lon": loc["longitude"]}

        # Image hashes (blur, sharpness, entropy)
        ih = conn.execute("SELECT blur_score, sharpness_score, edge_density, entropy FROM image_hashes WHERE image_uuid=?", (uuid,)).fetchone()
        if ih:
            rec["hashes"] = {"blur": round(float(ih["blur_score"] or 0), 1), "sharpness": round(float(ih["sharpness_score"] or 0), 1), "edge_density": round(float(ih["edge_density"] or 0), 3), "entropy": round(float(ih["entropy"] or 0), 2)}

        # Image analysis (brightness, dynamic range, noise, color temp)
        ia = conn.execute("SELECT mean_brightness, dynamic_range, noise_estimate, est_color_temp FROM image_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        if ia:
            rec["analysis"] = {"brightness": round(float(ia["mean_brightness"] or 0), 1), "dynamic_range": round(float(ia["dynamic_range"] or 0), 1), "noise": round(float(ia["noise_estimate"] or 0), 2), "color_temp": int(ia["est_color_temp"] or 0)}

        # Gemma picks (stories, crops, cartoon_style, mood, tags)
        gp = conn.execute(
            "SELECT gemma_json, gemma_description, gemma_mood, gemma_tags, crop_x, crop_y, crop_size, crop_reason, crops, story_silly, story_poetic, story_surrealist, story_noir, story_romantic, cartoon_style FROM gemma_picks WHERE uuid=?",
            (uuid,)
        ).fetchone()
        if gp:
            gemma = {}
            gemma["description"] = gp["gemma_description"] or ""
            gemma["mood"] = gp["gemma_mood"] or ""
            if gp["gemma_tags"]:
                try:
                    gemma["tags"] = json.loads(gp["gemma_tags"])
                except Exception:
                    gemma["tags"] = []
            stories = {}
            if gp["story_silly"]:
                stories["silly"] = gp["story_silly"]
            if gp["story_poetic"]:
                stories["poetic"] = gp["story_poetic"]
            if gp["story_surrealist"]:
                stories["surrealist"] = gp["story_surrealist"]
            if gp["story_noir"]:
                stories["noir"] = gp["story_noir"]
            if gp["story_romantic"]:
                stories["romantic"] = gp["story_romantic"]
            if stories:
                gemma["stories"] = stories
            if gp["crop_x"] is not None:
                gemma["crop_square"] = {"x": gp["crop_x"], "y": gp["crop_y"], "size": gp["crop_size"], "reason": gp["crop_reason"] or ""}
            if gp["crops"]:
                try:
                    gemma["crops"] = json.loads(gp["crops"])
                except Exception:
                    pass
            if gp["cartoon_style"]:
                gemma["cartoon_style"] = gp["cartoon_style"]
            rec["gemma"] = gemma

        images.append(rec)

    conn.close()
    return {
        "sample_size": len(images),
        "total_picks": total_picks,
        "images": images,
    }


def generate_embedding_audit_data():
    """Generate embedding audit data: 100 anchors with per-model neighbors."""
    import random
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    tbl, df = _get_lance()
    if tbl is None or df is None:
        conn.close()
        return {"anchor_count": 0, "neighbor_k": 6, "models": [], "anchors": []}

    # Get scenes for stratification
    scenes = conn.execute(
        "SELECT scene_1, COUNT(*) as cnt FROM scene_classification GROUP BY scene_1 ORDER BY cnt DESC LIMIT 20"
    ).fetchall()

    # Sample ~5 per scene to get ~100
    sample_uuids = []
    per_scene = max(3, 100 // max(len(scenes), 1))
    for scene_row in scenes:
        scene_name = scene_row["scene_1"]
        uuids = [r[0] for r in conn.execute(
            "SELECT image_uuid FROM scene_classification WHERE scene_1=? ORDER BY RANDOM() LIMIT ?",
            (scene_name, per_scene)
        ).fetchall()]
        # Only keep UUIDs that are in the vector store
        valid = [u for u in uuids if u in df["uuid"].values]
        sample_uuids.extend(valid)
        if len(sample_uuids) >= 100:
            break

    sample_uuids = sample_uuids[:100]

    models = ["DINOv2", "SigLIP", "CLIP", "Combined"]
    model_cols = [("dino", "DINOv2"), ("siglip", "SigLIP"), ("clip", "CLIP")]
    k = 6

    anchors = []
    for uuid in sample_uuids:
        matches = df[df["uuid"] == uuid]
        if matches.empty:
            continue
        query_row = matches.iloc[0]

        # Get metadata
        g = conn.execute("SELECT alt_text, vibe FROM gemini_analysis WHERE image_uuid=?", (uuid,)).fetchone()
        sc = conn.execute("SELECT scene_1 FROM scene_classification WHERE image_uuid=?", (uuid,)).fetchone()

        anchor = {
            "uuid": uuid,
            "thumb": f"/rendered/thumb/jpeg/{uuid}.jpg",
            "display": f"/rendered/display/jpeg/{uuid}.jpg",
            "caption": (g["alt_text"] or "") if g else "",
            "scene": (sc["scene_1"] or "") if sc else "",
            "vibes": [],
            "neighbors": {},
            "agreement": {},
        }
        if g and g["vibe"]:
            try:
                anchor["vibes"] = json.loads(g["vibe"])
            except:
                pass

        # Per-model neighbor search
        all_neighbor_sets = {}
        for col, name in model_cols:
            query_vec = query_row[col]
            results = tbl.search(query_vec, vector_column_name=col).limit(k + 1).to_pandas()
            neighbors = results[results["uuid"] != uuid].head(k)
            nb_list = []
            nb_uuids = set()
            for _, nb_row in neighbors.iterrows():
                nb_uuid = nb_row["uuid"]
                # Convert distance to similarity score (1 / (1 + dist))
                dist = float(nb_row["_distance"])
                score = round(1.0 / (1.0 + dist), 3)
                nb_list.append({
                    "uuid": nb_uuid,
                    "thumb": f"/rendered/thumb/jpeg/{nb_uuid}.jpg",
                    "score": score,
                })
                nb_uuids.add(nb_uuid)
            anchor["neighbors"][name] = nb_list
            all_neighbor_sets[name] = nb_uuids

        # Combined: average distances across models, re-rank
        try:
            import numpy as np
            combined_scores = {}
            for col, name in model_cols:
                query_vec = query_row[col]
                results = tbl.search(query_vec, vector_column_name=col).limit(30).to_pandas()
                for _, nb_row in results.iterrows():
                    nb_uuid = nb_row["uuid"]
                    if nb_uuid == uuid:
                        continue
                    dist = float(nb_row["_distance"])
                    score = 1.0 / (1.0 + dist)
                    combined_scores[nb_uuid] = combined_scores.get(nb_uuid, 0) + score / 3.0

            # Sort by combined score
            sorted_combined = sorted(combined_scores.items(), key=lambda x: -x[1])[:k]
            combined_list = []
            combined_uuids = set()
            for nb_uuid, score in sorted_combined:
                combined_list.append({
                    "uuid": nb_uuid,
                    "thumb": f"/rendered/thumb/jpeg/{nb_uuid}.jpg",
                    "score": round(score, 3),
                })
                combined_uuids.add(nb_uuid)
            anchor["neighbors"]["Combined"] = combined_list
            all_neighbor_sets["Combined"] = combined_uuids
        except Exception:
            anchor["neighbors"]["Combined"] = []
            all_neighbor_sets["Combined"] = set()

        # Agreement stats
        all_nb = set()
        for s in all_neighbor_sets.values():
            all_nb |= s
        shared_2plus = sum(1 for u in all_nb if sum(1 for s in all_neighbor_sets.values() if u in s) >= 2)
        shared_3plus = sum(1 for u in all_nb if sum(1 for s in all_neighbor_sets.values() if u in s) >= 3)
        anchor["agreement"] = {
            "shared_2plus": shared_2plus,
            "shared_3plus": shared_3plus,
            "unique_neighbors": len(all_nb),
        }

        anchors.append(anchor)

    conn.close()
    return {
        "anchor_count": len(anchors),
        "neighbor_k": k,
        "models": models,
        "anchors": anchors,
    }


def generate_collection_coverage_data():
    """Generate collection coverage data: which images appear in which experiences."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]

    # Load photos.json (exported gallery data)
    photos_path = PROJECT_ROOT / "frontend" / "show" / "data" / "photos.json"
    if not photos_path.exists():
        # Try alternate location
        photos_path = PROJECT_ROOT / "frontend" / "show" / "photos.json"

    photos = []
    if photos_path.exists():
        try:
            photos = json.loads(photos_path.read_text())
            if isinstance(photos, dict):
                photos = photos.get("photos", photos.get("images", []))
        except:
            pass

    # Define experience pools (approximate server-side)
    # Each experience filters differently
    experiences = []
    uuid_appearances = {}  # uuid -> count of experiences it appears in

    def count_pool(name, pool):
        """Register a pool of UUIDs for an experience."""
        uuids = set(p.get("uuid", p.get("id", "")) for p in pool if p.get("uuid") or p.get("id"))
        experiences.append({
            "name": name,
            "pool_size": len(uuids),
            "pct_of_collection": round(len(uuids) / total * 100, 1) if total else 0,
        })
        for u in uuids:
            uuid_appearances[u] = uuid_appearances.get(u, 0) + 1
        return uuids

    if photos:
        # Grid: all photos
        count_pool("Grid", photos)

        # Drift / Similarity: needs vectors — all photos with vectors
        count_pool("Drift", photos)

        # Colors: photos with palette data
        count_pool("Colors", [p for p in photos if p.get("palette") or p.get("colors")])

        # Bento: needs aspect ratio + aesthetic score > 6
        count_pool("Bento", [p for p in photos if (p.get("aesthetic") or p.get("score", 0)) >= 6])

        # Game: photos with multiple vibes
        count_pool("Game", [p for p in photos if len(p.get("vibes", [])) >= 2])

        # Stream: all photos (random stream)
        count_pool("Stream", photos)

        # Domino: photos with dominant colors
        count_pool("Domino", [p for p in photos if p.get("palette") or p.get("colors")])

        # Faces: photos with faces
        count_pool("Faces", [p for p in photos if p.get("faces") and len(p.get("faces", [])) > 0])

        # Compass: photos with scene data
        count_pool("Compass", [p for p in photos if p.get("scene")])

        # NYU: all photos (special layout)
        count_pool("NYU", photos)

        # Confetti: photos with aesthetic > 7
        count_pool("Confetti", [p for p in photos if (p.get("aesthetic") or p.get("score", 0)) >= 7])

        # Cinema: photos with cinematic style or high aesthetic
        count_pool("Cinema", [p for p in photos if (p.get("aesthetic") or p.get("score", 0)) >= 7.5 or p.get("style") == "cinematic"])

        # Reveal: all photos (random reveal)
        count_pool("Reveal", photos)

        # Sort By: uses photos.json (all)
        count_pool("Sort By", photos)

    # Sort experiences by pool size descending
    experiences.sort(key=lambda x: -x["pool_size"])

    # Distribution: how many images appear in N experiences
    max_appearances = max(uuid_appearances.values()) if uuid_appearances else 0
    distribution = []
    # Count images that appear in 0 experiences
    in_any = len(uuid_appearances)
    in_zero = total - in_any
    distribution.append({"appearances": 0, "count": in_zero})
    for n in range(1, max_appearances + 1):
        count = sum(1 for v in uuid_appearances.values() if v == n)
        if count > 0:
            distribution.append({"appearances": n, "count": count})

    # Dimension bias analysis
    dimensions = {}

    # Camera bias
    full_cameras = {}
    for r in conn.execute("SELECT camera_body, COUNT(*) as cnt FROM images GROUP BY camera_body ORDER BY cnt DESC").fetchall():
        full_cameras[r["camera_body"]] = round(r["cnt"] / total * 100, 1) if total else 0

    # Curated = photos that appear in at least one experience
    curated_uuids = set(uuid_appearances.keys())
    curated_total = len(curated_uuids)

    if curated_uuids and photos:
        curated_cameras = {}
        curated_scenes = {}
        curated_times = {}
        curated_styles = {}
        curated_gradings = {}

        photo_map = {p.get("uuid", p.get("id", "")): p for p in photos}
        for u in curated_uuids:
            p = photo_map.get(u, {})
            cam = p.get("camera", "")
            if cam:
                curated_cameras[cam] = curated_cameras.get(cam, 0) + 1
            scene = p.get("scene", "")
            if scene:
                curated_scenes[scene] = curated_scenes.get(scene, 0) + 1
            tod = p.get("time", p.get("time_of_day", ""))
            if tod:
                curated_times[tod] = curated_times.get(tod, 0) + 1
            st = p.get("style", "")
            if st:
                curated_styles[st] = curated_styles.get(st, 0) + 1
            gr = p.get("grading", "")
            if gr:
                curated_gradings[gr] = curated_gradings.get(gr, 0) + 1

        def to_pct(d, tot):
            return {k: round(v / tot * 100, 1) for k, v in sorted(d.items(), key=lambda x: -x[1])[:10]} if tot else {}

        # Full collection dimension distributions from DB
        full_scenes = {}
        for r in conn.execute("SELECT scene_1, COUNT(*) as cnt FROM scene_classification WHERE scene_1 IS NOT NULL GROUP BY scene_1 ORDER BY cnt DESC LIMIT 10").fetchall():
            full_scenes[r["scene_1"]] = round(r["cnt"] / total * 100, 1)

        full_times = {}
        for r in conn.execute("SELECT time_of_day, COUNT(*) as cnt FROM gemini_analysis WHERE time_of_day IS NOT NULL GROUP BY time_of_day ORDER BY cnt DESC").fetchall():
            full_times[r["time_of_day"]] = round(r["cnt"] / total * 100, 1)

        full_styles = {}
        for r in conn.execute("SELECT style, COUNT(*) as cnt FROM style_classification GROUP BY style ORDER BY cnt DESC LIMIT 10").fetchall():
            full_styles[r["style"]] = round(r["cnt"] / total * 100, 1)

        full_gradings = {}
        for r in conn.execute("SELECT grading_style, COUNT(*) as cnt FROM gemini_analysis WHERE grading_style IS NOT NULL AND raw_json != '' GROUP BY grading_style ORDER BY cnt DESC LIMIT 10").fetchall():
            full_gradings[r["grading_style"]] = round(r["cnt"] / total * 100, 1)

        dimensions = {
            "camera": {"full": full_cameras, "curated": to_pct(curated_cameras, curated_total)},
            "scene": {"full": full_scenes, "curated": to_pct(curated_scenes, curated_total)},
            "time_of_day": {"full": full_times, "curated": to_pct(curated_times, curated_total)},
            "style": {"full": full_styles, "curated": to_pct(curated_styles, curated_total)},
            "grading": {"full": full_gradings, "curated": to_pct(curated_gradings, curated_total)},
        }

    conn.close()
    return {
        "total": total,
        "in_at_least_one": in_any,
        "in_zero": in_zero,
        "pct_covered": round(in_any / total * 100, 1) if total else 0,
        "distribution": distribution,
        "experiences": experiences,
        "dimensions": dimensions,
    }


def generate_schema_data():
    """Return full DB schema: tables, columns, row counts, model attribution, sample values."""
    import os
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    db_size = os.path.getsize(str(DB_PATH))
    total_images = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]

    # Model attribution for each table
    model_map = {
        "images": {"model": "Import Pipeline", "category": "core", "description": "Master image table — one row per photograph with camera, format, dimensions, curation status"},
        "aesthetic_scores": {"model": "LAION Aesthetics (NIMA)", "category": "v1_signal", "description": "Aesthetic quality score 1-10. WARNING: nearly useless — avg 9.9, range 8.2-10.0, zero discrimination"},
        "aesthetic_scores_v2": {"model": "TOPIQ + MUSIQ + LAION", "category": "v2_signal", "description": "Three independent quality models combined into a composite score with real spread"},
        "quality_scores": {"model": "Technical + CLIP", "category": "v2_signal", "description": "Technical quality (sharpness, noise, exposure, contrast) + CLIP aesthetic alignment"},
        "depth_estimation": {"model": "Depth Anything v2 Large", "category": "v1_signal", "description": "Monocular depth estimation — near/mid/far percentages and scene complexity"},
        "scene_classification": {"model": "Places365", "category": "v1_signal", "description": "Scene type classification (top 3 scenes + environment label)"},
        "style_classification": {"model": "Rule-based classifier", "category": "v1_signal", "description": "Visual style labels (documentary, street, portrait, etc.)"},
        "image_captions": {"model": "BLIP2", "category": "v1_signal", "description": "Natural language image captions"},
        "florence_captions": {"model": "Florence-2-base", "category": "v2_signal", "description": "Three-tier captions: short, detailed, more detailed"},
        "ocr_detections": {"model": "EasyOCR", "category": "v1_signal", "description": "Text detected in images with bounding boxes and confidence"},
        "object_detections": {"model": "YOLOv8n", "category": "v1_signal", "description": "Object detection with labels, confidence, and bounding boxes"},
        "open_detections": {"model": "Grounding DINO tiny", "category": "v2_signal", "description": "Open-vocabulary object detection — no fixed label set, finds anything"},
        "face_detections": {"model": "YuNet / RetinaFace", "category": "v1_signal", "description": "Face locations with landmarks (eyes, nose, mouth) and area percentage"},
        "facial_emotions": {"model": "DeepFace", "category": "v1_signal", "description": "Dominant emotion per detected face with confidence scores"},
        "face_identities": {"model": "InsightFace ArcFace + DBSCAN", "category": "v2_signal", "description": "Face identity clustering — groups faces into identity clusters across images"},
        "dominant_colors": {"model": "K-means LAB clustering", "category": "v1_signal", "description": "Top 5 dominant colors per image with hex, RGB, LAB, percentage, and color name"},
        "image_tags": {"model": "CLIP zero-shot", "category": "v2_signal", "description": "Open-vocabulary tags via CLIP zero-shot classification (pipe-delimited)"},
        "exif_metadata": {"model": "EXIF Parser", "category": "v1_signal", "description": "Camera make/model, lens, focal length, aperture, shutter speed, ISO, GPS, date"},
        "image_hashes": {"model": "Perceptual Hashing", "category": "v1_signal", "description": "pHash, aHash, dHash, wHash for dedup + blur score, sharpness, edge density, entropy"},
        "image_analysis": {"model": "NumPy / OpenCV", "category": "v1_signal", "description": "Pixel-level stats: brightness, dynamic range, noise, color temperature, histogram"},
        "gemini_analysis": {"model": "Gemini 2.0 Flash", "category": "api_signal", "description": "Rich semantic analysis: exposure, composition, grading, time of day, weather, vibes, alt text"},
        "foreground_masks": {"model": "rembg u2net", "category": "v2_signal", "description": "Foreground/background segmentation with percentages and centroid"},
        "segmentation_masks": {"model": "SAM 2.1 hiera-tiny", "category": "v2_signal", "description": "Segment Anything — segment count, largest segment, complexity metrics"},
        "pose_detections": {"model": "YOLOv8n-pose", "category": "v2_signal", "description": "Human pose estimation with 17 keypoints per person"},
        "saliency_maps": {"model": "OpenCV Spectral Residual", "category": "v2_signal", "description": "Visual attention maps — peak saliency location, spread, center bias, rule-of-thirds"},
        "image_locations": {"model": "EXIF GPS extraction", "category": "v2_signal", "description": "Geocoded location names from GPS coordinates in EXIF data"},
        "border_crops": {"model": "OpenCV Edge Detection", "category": "v2_signal", "description": "Border/frame detection with crop suggestions and border percentage"},
        "enhancement_plans": {"model": "Signal-driven Engine v1", "category": "pipeline", "description": "Per-image enhancement strategy based on signal analysis"},
        "enhancement_plans_v2": {"model": "Signal-driven Engine v2", "category": "pipeline", "description": "V2 with depth/scene/style/vibe/face-aware adjustments"},
        "ai_variants": {"model": "Imagen 3 (Google)", "category": "api_signal", "description": "AI-generated image variants (cartoon style) from enhanced source images"},
        "tiers": {"model": "Render Pipeline", "category": "pipeline", "description": "Rendered image tiers (thumb, display, enhanced). WARNING: has duplicate rows per image"},
        "pipeline_runs": {"model": "Pipeline Orchestrator", "category": "pipeline", "description": "Pipeline execution history with status, timing, error messages"},
        "gcs_uploads": {"model": "GCS Upload Script", "category": "pipeline", "description": "Google Cloud Storage upload tracking"},
        "schema_version": {"model": "Database", "category": "core", "description": "Schema version tracking"},
    }

    tables = []
    total_rows = 0
    for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        name = t[0]
        cnt = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        total_rows += cnt

        columns = []
        for c in conn.execute(f"PRAGMA table_info([{name}])").fetchall():
            columns.append({"name": c[1], "type": c[2], "pk": bool(c[5])})

        meta = model_map.get(name, {"model": "Unknown", "category": "other", "description": ""})

        # Coverage: how many of 9011 images have data in this table
        has_uuid = any(col["name"] == "image_uuid" for col in columns)
        if has_uuid and name != "images":
            distinct = conn.execute(f"SELECT COUNT(DISTINCT image_uuid) FROM [{name}]").fetchone()[0]
            coverage = round(distinct / total_images * 100, 1) if total_images else 0
        elif name == "images":
            distinct = cnt
            coverage = 100.0
        else:
            distinct = None
            coverage = None

        # Sample values for interesting columns (skip blobs and long text)
        samples = {}
        skip_cols = {"raw_json", "raw_exif", "embedding", "plan_json", "exif_data",
                     "histogram_json", "keypoints_json", "segments_json", "bbox_json",
                     "emotion_scores", "confidence_json", "config", "error_message",
                     "prompt", "negative_prompt", "original_path", "local_path",
                     "gcs_url", "public_url", "gcs_path", "output_path"}
        for col in columns[:8]:  # First 8 columns max
            if col["name"] in skip_cols or col["name"].endswith("_at"):
                continue
            try:
                vals = conn.execute(
                    f"SELECT DISTINCT [{col['name']}] FROM [{name}] WHERE [{col['name']}] IS NOT NULL LIMIT 5"
                ).fetchall()
                if vals:
                    sample_vals = []
                    for v in vals:
                        val = v[0]
                        if isinstance(val, str) and len(val) > 60:
                            val = val[:60] + "..."
                        elif isinstance(val, bytes):
                            continue
                        sample_vals.append(val)
                    if sample_vals:
                        samples[col["name"]] = sample_vals
            except:
                pass

        tables.append({
            "name": name,
            "rows": cnt,
            "columns": columns,
            "col_count": len(columns),
            "model": meta["model"],
            "category": meta["category"],
            "description": meta["description"],
            "coverage": coverage,
            "distinct_images": distinct,
            "samples": samples,
        })

    conn.close()

    # Category summaries
    categories = {}
    for t in tables:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "rows": 0, "tables": []}
        categories[cat]["count"] += 1
        categories[cat]["rows"] += t["rows"]
        categories[cat]["tables"].append(t["name"])

    return {
        "db_path": str(DB_PATH),
        "db_size": db_size,
        "total_images": total_images,
        "table_count": len(tables),
        "total_rows": total_rows,
        "categories": categories,
        "tables": tables,
    }
