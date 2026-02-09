import Foundation
import AppKit

// MARK: - Quick Counts (pre-computed for sidebar)

struct QuickCounts {
    var people: Int = 0
    var animals: Int = 0
    var noSubject: Int = 0
    var monochrome: Int = 0
    var color: Int = 0
    var withText: Int = 0
}

// MARK: - Semantic Pop

struct SemanticPop: Identifiable, Hashable {
    let id: String
    let color: String
    let object: String
    let impact: String

    var nsColor: NSColor {
        let name = color.lowercased()
        switch name {
        case "red": return .systemRed
        case "orange": return .systemOrange
        case "yellow": return .systemYellow
        case "green": return .systemGreen
        case "blue": return .systemBlue
        case "purple": return .systemPurple
        case "pink": return .systemPink
        case "brown": return .systemBrown
        case "white": return .white
        case "black": return NSColor(white: 0.15, alpha: 1)
        case "gray", "grey": return .systemGray
        default: return .systemGray
        }
    }
}

// MARK: - Photo

struct PhotoItem: Identifiable, Hashable {
    let id: String          // image_uuid
    let originalPath: String
    let filename: String
    let category: String
    let subcategory: String?
    let sourceFormat: String
    let width: Int
    let height: Int
    let aspectRatio: Double
    let orientation: String
    let originalSize: Int

    // Camera metadata
    var cameraBody: String?
    var filmStock: String?
    var medium: String?
    var isMonochrome: Bool

    // Gemini analysis (optional)
    var exposure: String?
    var sharpness: String?
    var compositionTechnique: String?
    var depth: String?
    var gradingStyle: String?
    var timeOfDay: String?
    var setting: String?
    var weather: String?
    var facesCount: Int?
    var vibe: String?
    var altText: String?
    var shouldRotate: String?
    var semanticPops: String?
    var colorPaletteJSON: String?
    var analyzedAt: String?

    // Tier paths (from DB)
    var thumbPath: String?
    var displayPath: String?

    // Curation
    var curatedStatus: String

    // --- NEW: Location ---
    var locationName: String?
    var latitude: Double?
    var longitude: Double?
    var locationSource: String?      // gps_exif / user_manual / propagated
    var locationConfidence: Double?
    var locationAccepted: Bool = false
    var propagatedFrom: String?

    // --- NEW: Aesthetic score ---
    var aestheticScore: Double?
    var aestheticLabel: String?

    // --- NEW: Depth estimation ---
    var depthNearPct: Double?
    var depthMidPct: Double?
    var depthFarPct: Double?
    var depthComplexity: Double?

    // --- NEW: Scene classification ---
    var scene1: String?
    var scene1Score: Double?
    var scene2: String?
    var scene2Score: Double?
    var scene3: String?
    var scene3Score: Double?

    // --- NEW: Style classification ---
    var styleLabel: String?
    var styleConfidence: Double?

    // --- NEW: Caption ---
    var blipCaption: String?

    // --- NEW: OCR ---
    var ocrText: String?

    // --- NEW: Facial emotions ---
    var emotionsSummary: String?

    // --- NEW: EXIF date + GPS ---
    var dateTaken: String?
    var exifGPSLat: Double?
    var exifGPSLon: Double?

    // --- NEW: Enhancement metrics ---
    var enhancementStatus: String?
    var enhPreBrightness: Double?
    var enhPostBrightness: Double?
    var enhPreWBShift: Double?
    var enhPostWBShift: Double?
    var enhPreContrast: Double?
    var enhPostContrast: Double?

    // --- NEW: Object/face counts from detection ---
    var detectedObjectCount: Int?
    var detectedFaceCount: Int?
    var detectedPersonCount: Int = 0
    var detectedAnimalCount: Int = 0

    // --- Quality scores ---
    var qualityTechnical: Double?
    var qualityClip: Double?
    var qualityCombined: Double?

    // --- Display variant ---
    var displayVariant: String = "original"

    // --- Cached (populated by prepareCache) ---
    var isAnalyzed: Bool = false
    var hasLocation: Bool = false
    var hasOCRText: Bool = false
    var hasPeople: Bool = false
    var hasAnimal: Bool = false
    var folderPath: String = ""
    var cachedVibeList: [String] = []
    var cachedEmotionList: [String] = []
    var cachedPaletteSaturation: Double = 0
    var cachedPaletteBrightness: Double = 0
    var cachedAestheticBucket: String?
    var cachedPaletteColors: [NSColor] = []

    var hasEnhancement: Bool { enhancementStatus != nil }
    var isEnhanced: Bool { enhancementStatus == "enhanced" }
    var hasCropped: Bool = false

    var dimensionLabel: String { "\(width)×\(height)" }
    var ratioLabel: String {
        let r = aspectRatio
        if abs(r - 1.778) < 0.01 { return "16:9" }
        if abs(r - 1.5) < 0.02 { return "3:2" }
        if abs(r - 1.333) < 0.01 { return "4:3" }
        if abs(r - 0.667) < 0.01 { return "2:3" }
        if abs(r - 0.75) < 0.01 { return "3:4" }
        if abs(r - 0.5625) < 0.01 { return "9:16" }
        if abs(r - 1.0) < 0.01 { return "1:1" }
        return String(format: "%.2f", r)
    }
    var vibeList: [String] { cachedVibeList }
    var emotionList: [String] { cachedEmotionList }
    var paletteSaturation: Double { cachedPaletteSaturation }
    var paletteBrightness: Double { cachedPaletteBrightness }
    var aestheticBucket: String? { cachedAestheticBucket }
    var paletteColors: [NSColor] { cachedPaletteColors }
    var sizeLabel: String {
        String(format: "%.1f MB", Double(originalSize) / 1_048_576.0)
    }

    /// Call once after loading from DB to pre-compute expensive properties
    mutating func prepareCache() {
        isAnalyzed = analyzedAt != nil
        hasLocation = locationName != nil || latitude != nil
        hasOCRText = ocrText != nil && !(ocrText?.isEmpty ?? true)
        hasPeople = detectedPersonCount > 0 || (detectedFaceCount ?? 0) > 0
        hasAnimal = detectedAnimalCount > 0
        folderPath = {
            if let sub = subcategory, !sub.isEmpty { return "\(category)/\(sub)" }
            return category
        }()

        // Vibes
        if let v = vibe, let data = v.data(using: .utf8),
           let arr = try? JSONSerialization.jsonObject(with: data) as? [String] {
            cachedVibeList = arr
        }

        // Emotions
        if let e = emotionsSummary, !e.isEmpty {
            cachedEmotionList = Array(Set(e.components(separatedBy: ", ").map { $0.trimmingCharacters(in: .whitespaces) }))
        }

        // Aesthetic bucket
        if let s = aestheticScore {
            if s >= 7.0 { cachedAestheticBucket = "Excellent" }
            else if s >= 5.0 { cachedAestheticBucket = "Good" }
            else if s >= 3.0 { cachedAestheticBucket = "Average" }
            else { cachedAestheticBucket = "Poor" }
        }

        // Palette colors + saturation + brightness
        if let json = colorPaletteJSON, let data = json.data(using: .utf8),
           let arr = try? JSONSerialization.jsonObject(with: data) as? [String] {
            let colors = arr.compactMap { NSColor.fromHex($0) }
            cachedPaletteColors = colors
            if !colors.isEmpty {
                var satTotal = 0.0, briTotal = 0.0
                for c in colors {
                    let rgb = c.usingColorSpace(.sRGB) ?? c
                    var h: CGFloat = 0, s: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
                    rgb.getHue(&h, saturation: &s, brightness: &b, alpha: &a)
                    satTotal += Double(s)
                    briTotal += Double(b)
                }
                cachedPaletteSaturation = satTotal / Double(colors.count)
                cachedPaletteBrightness = briTotal / Double(colors.count)
            }
        }
    }

    /// Parse semantic pops from JSON array
    var semanticPopsList: [SemanticPop] {
        guard let s = semanticPops, let data = s.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: String]] else {
            return []
        }
        return arr.enumerated().map { idx, dict in
            SemanticPop(
                id: "\(id)-pop-\(idx)",
                color: dict["color"] ?? "gray",
                object: dict["object"] ?? "",
                impact: dict["impact"] ?? "Low"
            )
        }
    }

    /// Aesthetic score as star rating (1-10 → 0.5-5.0 stars)
    var aestheticStars: Double? {
        guard let s = aestheticScore else { return nil }
        return max(0.5, min(5.0, s / 2.0))
    }

    /// Top scenes as array
    var scenesList: [(String, Double)] {
        var result: [(String, Double)] = []
        if let s = scene1, let sc = scene1Score { result.append((s, sc)) }
        if let s = scene2, let sc = scene2Score { result.append((s, sc)) }
        if let s = scene3, let sc = scene3Score { result.append((s, sc)) }
        return result
    }
}

// MARK: - NSColor hex helper

extension NSColor {
    static func fromHex(_ hex: String) -> NSColor? {
        var h = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if h.hasPrefix("#") { h = String(h.dropFirst()) }
        guard h.count == 6, let val = UInt64(h, radix: 16) else { return nil }
        return NSColor(
            red: CGFloat((val >> 16) & 0xFF) / 255.0,
            green: CGFloat((val >> 8) & 0xFF) / 255.0,
            blue: CGFloat(val & 0xFF) / 255.0,
            alpha: 1.0
        )
    }
}

// MARK: - Sort

enum SortOption: String, CaseIterable {
    case random = "Random"
    case quality = "Quality"
    case aesthetic = "Aesthetic"
    case date = "Date"
    case exposure = "Exposure"
    case saturation = "Saturation"
    case depth = "Depth"
    case brightness = "Brightness"
    case faces = "Faces"

    var icon: String {
        switch self {
        case .random: return "shuffle"
        case .quality: return "sparkles"
        case .aesthetic: return "star"
        case .date: return "calendar"
        case .exposure: return "sun.max"
        case .saturation: return "drop.halffull"
        case .depth: return "cube"
        case .brightness: return "sun.min"
        case .faces: return "person.2"
        }
    }
}

// MARK: - Query

enum QueryMode: String, CaseIterable {
    case union = "Any"
    case intersection = "All"
}

enum FilterDimension: Hashable {
    case category, subcategory, orientation, sourceFormat, camera
    case curation, analysis, grading, vibe, time, setting
    case exposure, depth, composition, search
    case location, style, aesthetic, hasText
    case weather, scene, emotion
    case medium, monochrome, enhancement, filmStock
}

struct FilterState {
    var categories: Set<String> = []
    var subcategories: Set<String> = []
    var orientations: Set<String> = []
    var sourceFormats: Set<String> = []
    var cameras: Set<String> = []
    var gradingStyles: Set<String> = []
    var vibes: Set<String> = []
    var timesOfDay: Set<String> = []
    var settings: Set<String> = []
    var exposures: Set<String> = []
    var depths: Set<String> = []
    var compositions: Set<String> = []
    var curatedStatuses: Set<String> = []
    var analysisStatus: String?
    var searchText: String = ""
    var locations: Set<String> = []
    var styles: Set<String> = []
    var aestheticBuckets: Set<String> = []
    var hasTextFilter: String?  // "yes" / "no" / nil
    var weathers: Set<String> = []
    var scenes: Set<String> = []
    var emotions: Set<String> = []
    var mediums: Set<String> = []
    var monochromeFilter: String?  // "yes" / "no" / nil
    var subjectFilter: String?  // "people" / "animal" / "none" / nil
    var enhancements: Set<String> = []
    var filmStocks: Set<String> = []
    var dimensionModes: [FilterDimension: QueryMode] = [:]

    func mode(for dim: FilterDimension) -> QueryMode { dimensionModes[dim] ?? .union }
    mutating func setMode(_ mode: QueryMode, for dim: FilterDimension) { dimensionModes[dim] = mode }

    var isActive: Bool {
        !categories.isEmpty || !subcategories.isEmpty || !orientations.isEmpty ||
        !sourceFormats.isEmpty || !cameras.isEmpty || !gradingStyles.isEmpty ||
        !vibes.isEmpty || !timesOfDay.isEmpty || !settings.isEmpty ||
        !exposures.isEmpty || !depths.isEmpty || !compositions.isEmpty ||
        !curatedStatuses.isEmpty || analysisStatus != nil || !searchText.isEmpty ||
        !locations.isEmpty || !styles.isEmpty || !aestheticBuckets.isEmpty ||
        hasTextFilter != nil || !weathers.isEmpty || !scenes.isEmpty || !emotions.isEmpty ||
        !mediums.isEmpty || monochromeFilter != nil || subjectFilter != nil || !enhancements.isEmpty || !filmStocks.isEmpty
    }

    mutating func toggle(_ keyPath: WritableKeyPath<FilterState, Set<String>>, _ value: String) {
        if self[keyPath: keyPath].contains(value) {
            self[keyPath: keyPath].remove(value)
        } else {
            self[keyPath: keyPath].insert(value)
        }
    }

    mutating func clear() {
        categories = []; subcategories = []; orientations = []
        sourceFormats = []; cameras = []; gradingStyles = []; vibes = []
        timesOfDay = []; settings = []; exposures = []
        depths = []; compositions = []; curatedStatuses = []
        analysisStatus = nil; searchText = ""
        locations = []; styles = []; aestheticBuckets = []
        hasTextFilter = nil
        weathers = []; scenes = []; emotions = []
        mediums = []; monochromeFilter = nil; subjectFilter = nil; enhancements = []; filmStocks = []
        dimensionModes = [:]
    }
}

// MARK: - Faceted Options

struct FacetOption: Identifiable, Hashable {
    var id: String { value }
    let value: String
    let count: Int
}

struct FacetedOptions {
    var categories: [FacetOption] = []
    var subcategories: [FacetOption] = []
    var orientations: [FacetOption] = []
    var sourceFormats: [FacetOption] = []
    var cameras: [FacetOption] = []
    var curatedStatuses: [FacetOption] = []
    var gradingStyles: [FacetOption] = []
    var vibes: [FacetOption] = []
    var timesOfDay: [FacetOption] = []
    var settings: [FacetOption] = []
    var exposures: [FacetOption] = []
    var depths: [FacetOption] = []
    var compositions: [FacetOption] = []
    var locations: [FacetOption] = []
    var styles: [FacetOption] = []
    var aestheticBuckets: [FacetOption] = []
    var weathers: [FacetOption] = []
    var scenes: [FacetOption] = []
    var emotions: [FacetOption] = []
    var mediums: [FacetOption] = []
    var enhancements: [FacetOption] = []
    var filmStocks: [FacetOption] = []
}

// MARK: - Query Bar Chips

struct ActiveChip: Identifiable {
    let id: String
    let label: String
}

struct ChipGroup: Identifiable {
    let id: String
    let chips: [ActiveChip]
    let mode: QueryMode
}
