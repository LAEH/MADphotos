import Foundation
import SQLite3

final class Database {
    private var db: OpaquePointer?
    let basePath: String  // MADphotos root

    init(basePath: String) {
        self.basePath = basePath
        let dbPath = (basePath as NSString).appendingPathComponent("mad_photos.db")
        if sqlite3_open_v2(dbPath, &db, SQLITE_OPEN_READWRITE, nil) != SQLITE_OK {
            print("ERROR: Could not open database at \(dbPath)")
        }
        ensureCuratedColumn()
    }

    deinit {
        sqlite3_close(db)
    }

    // ------------------------------------------------------------------
    // Schema migration — add curated_status column if missing
    // ------------------------------------------------------------------

    private func ensureCuratedColumn() {
        var stmt: OpaquePointer?
        let sql = "PRAGMA table_info(images)"
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            var found = false
            while sqlite3_step(stmt) == SQLITE_ROW {
                if let name = sqlite3_column_text(stmt, 1) {
                    if String(cString: name) == "curated_status" { found = true }
                }
            }
            sqlite3_finalize(stmt)
            if !found {
                exec("ALTER TABLE images ADD COLUMN curated_status TEXT DEFAULT 'pending'")
            }
        }
    }

    @discardableResult
    private func exec(_ sql: String) -> Bool {
        var err: UnsafeMutablePointer<CChar>?
        let rc = sqlite3_exec(db, sql, nil, nil, &err)
        if rc != SQLITE_OK {
            if let e = err { print("SQL error: \(String(cString: e))"); sqlite3_free(e) }
            return false
        }
        return true
    }

    // ------------------------------------------------------------------
    // Load all photos with all signal JOINs
    // ------------------------------------------------------------------

    func loadPhotos() -> [PhotoItem] {
        var photos: [PhotoItem] = []
        // Column indices documented inline
        let sql = """
            SELECT
                i.uuid,                          -- 0
                i.original_path,                 -- 1
                i.filename,                      -- 2
                i.category,                      -- 3
                i.subcategory,                   -- 4
                i.source_format,                 -- 5
                i.width,                         -- 6
                i.height,                        -- 7
                i.aspect_ratio,                  -- 8
                i.orientation,                   -- 9
                i.original_size_bytes,           -- 10
                COALESCE(i.curated_status, 'pending'), -- 11
                g.exposure,                      -- 12
                g.sharpness,                     -- 13
                g.composition_technique,         -- 14
                g.depth,                         -- 15
                g.grading_style,                 -- 16
                g.time_of_day,                   -- 17
                g.setting,                       -- 18
                g.weather,                       -- 19
                g.faces_count,                   -- 20
                g.vibe,                          -- 21
                g.alt_text,                      -- 22
                g.should_rotate,                 -- 23
                g.semantic_pops,                 -- 24
                g.analyzed_at,                   -- 25
                t_thumb.local_path,              -- 26
                t_display.local_path,            -- 27
                i.camera_body,                   -- 28
                i.film_stock,                    -- 29
                i.medium,                        -- 30
                COALESCE(i.is_monochrome, 0),    -- 31
                json_extract(g.raw_json, '$.color.palette'), -- 32
                -- Location
                loc.location_name,               -- 33
                loc.latitude,                    -- 34
                loc.longitude,                   -- 35
                loc.source,                      -- 36
                loc.confidence,                  -- 37
                COALESCE(loc.accepted, 0),       -- 38
                loc.propagated_from,             -- 39
                -- Aesthetic
                aes.score,                       -- 40
                aes.score_label,                 -- 41
                -- Depth estimation
                dep.near_pct,                    -- 42
                dep.mid_pct,                     -- 43
                dep.far_pct,                     -- 44
                dep.depth_complexity,            -- 45
                -- Scene
                sc.scene_1,                      -- 46
                sc.score_1,                      -- 47
                sc.scene_2,                      -- 48
                sc.score_2,                      -- 49
                sc.scene_3,                      -- 50
                sc.score_3,                      -- 51
                -- Style
                sty.style,                       -- 52
                sty.confidence,                  -- 53
                -- Caption
                cap.caption,                     -- 54
                -- EXIF
                ex.date_taken,                   -- 55
                ex.gps_lat,                      -- 56
                ex.gps_lon,                      -- 57
                -- Enhancement
                enh.status,                      -- 58
                enh.pre_brightness,              -- 59
                enh.post_brightness,             -- 60
                enh.pre_wb_shift_r,              -- 61
                enh.post_wb_shift_r,             -- 62
                enh.pre_contrast,                -- 63
                enh.post_contrast,               -- 64
                -- Object/face counts (subqueries)
                (SELECT COUNT(*) FROM object_detections od WHERE od.image_uuid = i.uuid), -- 65
                (SELECT COUNT(*) FROM face_detections fd WHERE fd.image_uuid = i.uuid),   -- 66
                -- OCR (aggregated)
                (SELECT GROUP_CONCAT(oc.text, ' ') FROM ocr_detections oc WHERE oc.image_uuid = i.uuid), -- 67
                -- Emotions (aggregated)
                (SELECT GROUP_CONCAT(fe.dominant_emotion, ', ') FROM facial_emotions fe WHERE fe.image_uuid = i.uuid) -- 68
            FROM images i
            LEFT JOIN gemini_analysis g ON i.uuid = g.image_uuid
                AND g.raw_json IS NOT NULL AND g.raw_json != ''
            LEFT JOIN tiers t_thumb ON i.uuid = t_thumb.image_uuid
                AND t_thumb.tier_name = 'thumb' AND t_thumb.format = 'jpeg' AND t_thumb.variant_id IS NULL
            LEFT JOIN tiers t_display ON i.uuid = t_display.image_uuid
                AND t_display.tier_name = 'display' AND t_display.format = 'jpeg' AND t_display.variant_id IS NULL
            LEFT JOIN image_locations loc ON i.uuid = loc.image_uuid
            LEFT JOIN aesthetic_scores aes ON i.uuid = aes.image_uuid
            LEFT JOIN depth_estimation dep ON i.uuid = dep.image_uuid
            LEFT JOIN scene_classification sc ON i.uuid = sc.image_uuid
            LEFT JOIN style_classification sty ON i.uuid = sty.image_uuid
            LEFT JOIN image_captions cap ON i.uuid = cap.image_uuid
            LEFT JOIN exif_metadata ex ON i.uuid = ex.image_uuid
            LEFT JOIN enhancement_plans enh ON i.uuid = enh.image_uuid
            ORDER BY i.category, i.subcategory, i.filename
        """
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            if let errMsg = sqlite3_errmsg(db) {
                print("SQL prepare error: \(String(cString: errMsg))")
            }
            return photos
        }

        while sqlite3_step(stmt) == SQLITE_ROW {
            let item = PhotoItem(
                id: col(stmt, 0) ?? "",
                originalPath: col(stmt, 1) ?? "",
                filename: col(stmt, 2) ?? "",
                category: col(stmt, 3) ?? "",
                subcategory: col(stmt, 4),
                sourceFormat: col(stmt, 5) ?? "",
                width: Int(sqlite3_column_int(stmt, 6)),
                height: Int(sqlite3_column_int(stmt, 7)),
                aspectRatio: sqlite3_column_double(stmt, 8),
                orientation: col(stmt, 9) ?? "",
                originalSize: Int(sqlite3_column_int(stmt, 10)),
                cameraBody: col(stmt, 28),
                filmStock: col(stmt, 29),
                medium: col(stmt, 30),
                isMonochrome: Int(sqlite3_column_int(stmt, 31)) != 0,
                exposure: col(stmt, 12),
                sharpness: col(stmt, 13),
                compositionTechnique: col(stmt, 14),
                depth: col(stmt, 15),
                gradingStyle: col(stmt, 16),
                timeOfDay: col(stmt, 17),
                setting: col(stmt, 18),
                weather: col(stmt, 19),
                facesCount: sqlite3_column_type(stmt, 20) != SQLITE_NULL ? Int(sqlite3_column_int(stmt, 20)) : nil,
                vibe: col(stmt, 21),
                altText: col(stmt, 22),
                shouldRotate: col(stmt, 23),
                semanticPops: col(stmt, 24),
                colorPaletteJSON: col(stmt, 32),
                analyzedAt: col(stmt, 25),
                thumbPath: col(stmt, 26),
                displayPath: col(stmt, 27),
                curatedStatus: col(stmt, 11) ?? "pending",
                // Location
                locationName: col(stmt, 33),
                latitude: dblOrNil(stmt, 34),
                longitude: dblOrNil(stmt, 35),
                locationSource: col(stmt, 36),
                locationConfidence: dblOrNil(stmt, 37),
                locationAccepted: Int(sqlite3_column_int(stmt, 38)) != 0,
                propagatedFrom: col(stmt, 39),
                // Aesthetic
                aestheticScore: dblOrNil(stmt, 40),
                aestheticLabel: col(stmt, 41),
                // Depth
                depthNearPct: dblOrNil(stmt, 42),
                depthMidPct: dblOrNil(stmt, 43),
                depthFarPct: dblOrNil(stmt, 44),
                depthComplexity: dblOrNil(stmt, 45),
                // Scene
                scene1: col(stmt, 46),
                scene1Score: dblOrNil(stmt, 47),
                scene2: col(stmt, 48),
                scene2Score: dblOrNil(stmt, 49),
                scene3: col(stmt, 50),
                scene3Score: dblOrNil(stmt, 51),
                // Style
                styleLabel: col(stmt, 52),
                styleConfidence: dblOrNil(stmt, 53),
                // Caption
                blipCaption: col(stmt, 54),
                // OCR
                ocrText: col(stmt, 67),
                // Emotions
                emotionsSummary: col(stmt, 68),
                // EXIF
                dateTaken: col(stmt, 55),
                exifGPSLat: dblOrNil(stmt, 56),
                exifGPSLon: dblOrNil(stmt, 57),
                // Enhancement
                enhancementStatus: col(stmt, 58),
                enhPreBrightness: dblOrNil(stmt, 59),
                enhPostBrightness: dblOrNil(stmt, 60),
                enhPreWBShift: dblOrNil(stmt, 61),
                enhPostWBShift: dblOrNil(stmt, 62),
                enhPreContrast: dblOrNil(stmt, 63),
                enhPostContrast: dblOrNil(stmt, 64),
                // Detection counts
                detectedObjectCount: intOrNil(stmt, 65),
                detectedFaceCount: intOrNil(stmt, 66)
            )
            photos.append(item)
        }
        sqlite3_finalize(stmt)
        return photos
    }

    private func col(_ stmt: OpaquePointer?, _ idx: Int32) -> String? {
        guard let ptr = sqlite3_column_text(stmt, idx) else { return nil }
        return String(cString: ptr)
    }

    private func dblOrNil(_ stmt: OpaquePointer?, _ idx: Int32) -> Double? {
        if sqlite3_column_type(stmt, idx) == SQLITE_NULL { return nil }
        return sqlite3_column_double(stmt, idx)
    }

    private func intOrNil(_ stmt: OpaquePointer?, _ idx: Int32) -> Int? {
        if sqlite3_column_type(stmt, idx) == SQLITE_NULL { return nil }
        return Int(sqlite3_column_int(stmt, idx))
    }

    // ------------------------------------------------------------------
    // Update curation status
    // ------------------------------------------------------------------

    func setCuratedStatus(uuid: String, status: String) {
        let sql = "UPDATE images SET curated_status = ? WHERE uuid = ?"
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, (status as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 2, (uuid as NSString).utf8String, -1, nil)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
        }
    }

    // ------------------------------------------------------------------
    // Location methods
    // ------------------------------------------------------------------

    func setLocation(uuid: String, name: String, lat: Double?, lon: Double?, source: String) {
        let now = ISO8601DateFormatter().string(from: Date())
        let sql = """
            INSERT INTO image_locations (image_uuid, location_name, latitude, longitude, source, confidence, accepted, created_at)
            VALUES (?, ?, ?, ?, ?, 1.0, 1, ?)
            ON CONFLICT(image_uuid) DO UPDATE SET
                location_name=excluded.location_name, latitude=excluded.latitude,
                longitude=excluded.longitude, source=excluded.source,
                confidence=excluded.confidence, accepted=excluded.accepted,
                created_at=excluded.created_at
        """
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, (uuid as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 2, (name as NSString).utf8String, -1, nil)
            if let lat = lat { sqlite3_bind_double(stmt, 3, lat) } else { sqlite3_bind_null(stmt, 3) }
            if let lon = lon { sqlite3_bind_double(stmt, 4, lon) } else { sqlite3_bind_null(stmt, 4) }
            sqlite3_bind_text(stmt, 5, (source as NSString).utf8String, -1, nil)
            sqlite3_bind_text(stmt, 6, (now as NSString).utf8String, -1, nil)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
        }
    }

    /// Propagate location to nearby images (same camera, date within ±7 days)
    func propagateLocation(fromUUID: String, locationName: String, cameraBody: String, dateTaken: String) -> Int {
        let now = ISO8601DateFormatter().string(from: Date())
        // Find same camera, date within ±7 days, no accepted location
        let sql = """
            INSERT OR IGNORE INTO image_locations (image_uuid, location_name, source, confidence, propagated_from, accepted, created_at)
            SELECT ex.image_uuid, ?, 'propagated',
                CASE
                    WHEN ABS(julianday(ex.date_taken) - julianday(?)) < 1 THEN 0.95
                    WHEN ABS(julianday(ex.date_taken) - julianday(?)) < 2 THEN 0.85
                    WHEN ABS(julianday(ex.date_taken) - julianday(?)) < 4 THEN 0.70
                    ELSE 0.60
                END,
                ?, 0, ?
            FROM exif_metadata ex
            JOIN images i ON ex.image_uuid = i.uuid
            WHERE i.camera_body = ?
                AND ex.date_taken IS NOT NULL
                AND ABS(julianday(ex.date_taken) - julianday(?)) <= 7
                AND ex.image_uuid != ?
                AND ex.image_uuid NOT IN (
                    SELECT image_uuid FROM image_locations WHERE accepted = 1
                )
        """
        var stmt: OpaquePointer?
        var count = 0
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            var idx: Int32 = 1
            sqlite3_bind_text(stmt, idx, (locationName as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (dateTaken as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (dateTaken as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (dateTaken as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (fromUUID as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (now as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (cameraBody as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (dateTaken as NSString).utf8String, -1, nil); idx += 1
            sqlite3_bind_text(stmt, idx, (fromUUID as NSString).utf8String, -1, nil); idx += 1
            sqlite3_step(stmt)
            count = Int(sqlite3_changes(db))
            sqlite3_finalize(stmt)
        }
        return count
    }

    func acceptLocation(uuid: String) {
        let sql = "UPDATE image_locations SET accepted = 1 WHERE image_uuid = ?"
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, (uuid as NSString).utf8String, -1, nil)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
        }
    }

    func rejectLocation(uuid: String) {
        let sql = "DELETE FROM image_locations WHERE image_uuid = ? AND source = 'propagated'"
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
            sqlite3_bind_text(stmt, 1, (uuid as NSString).utf8String, -1, nil)
            sqlite3_step(stmt)
            sqlite3_finalize(stmt)
        }
    }

    // ------------------------------------------------------------------
    // Filter option counts
    // ------------------------------------------------------------------

    func distinctValues(column: String, table: String = "images") -> [(String, Int)] {
        var results: [(String, Int)] = []
        let sql = "SELECT \(column), COUNT(*) as c FROM \(table) WHERE \(column) IS NOT NULL AND \(column) != '' GROUP BY \(column) ORDER BY c DESC"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return results }
        while sqlite3_step(stmt) == SQLITE_ROW {
            if let val = col(stmt, 0) {
                results.append((val, Int(sqlite3_column_int(stmt, 1))))
            }
        }
        sqlite3_finalize(stmt)
        return results
    }

    func curationCounts() -> (total: Int, kept: Int, rejected: Int, pending: Int) {
        var total = 0, kept = 0, rejected = 0, pending = 0
        let sql = "SELECT COALESCE(curated_status, 'pending'), COUNT(*) FROM images GROUP BY curated_status"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return (0,0,0,0) }
        while sqlite3_step(stmt) == SQLITE_ROW {
            let status = col(stmt, 0) ?? "pending"
            let count = Int(sqlite3_column_int(stmt, 1))
            total += count
            switch status {
            case "kept": kept = count
            case "rejected": rejected = count
            default: pending += count
            }
        }
        sqlite3_finalize(stmt)
        return (total, kept, rejected, pending)
    }
}
