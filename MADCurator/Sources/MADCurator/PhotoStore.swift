import Foundation
import SwiftUI
import AppKit

@MainActor
final class PhotoStore: ObservableObject {
    let database: Database
    let basePath: String

    @Published var allPhotos: [PhotoItem] = []
    @Published var filteredPhotos: [PhotoItem] = []
    @Published var filters = FilterState()
    @Published var options = FacetedOptions()
    @Published var selectedPhoto: PhotoItem?
    @Published var selectedIndex: Int = -1
    @Published var curationCounts: (total: Int, kept: Int, rejected: Int, pending: Int) = (0,0,0,0)

    // Enhanced image toggle
    @Published var showEnhanced: Bool = false
    // Fullscreen mode
    @Published var isFullscreen: Bool = false
    // Info panel visibility
    @Published var showInfoPanel: Bool = true

    private var thumbCache = NSCache<NSString, NSImage>()

    init(basePath: String) {
        self.basePath = basePath
        self.database = Database(basePath: basePath)
        thumbCache.countLimit = 2000
    }

    func load() {
        allPhotos = database.loadPhotos()
        filters.analysisStatus = "analyzed"
        applyFilters()
        refreshCounts()
    }

    func refreshCounts() {
        curationCounts = database.curationCounts()
    }

    // MARK: - Core filter engine

    func applyFilters() {
        filteredPhotos = allPhotos.filter { matchesFilters($0) }
        computeFacetedOptions()
        if let sel = selectedPhoto, !filteredPhotos.contains(sel) {
            selectedPhoto = nil; selectedIndex = -1
        }
    }

    /// Matches a photo against all active filters.
    /// Pass `excluding:` to skip one dimension (used for faceted option counts).
    private func matchesFilters(_ p: PhotoItem, excluding dim: FilterDimension? = nil) -> Bool {
        let f = filters
        if dim != .category && !f.categories.isEmpty && !f.categories.contains(p.category) { return false }
        if dim != .subcategory && !f.subcategories.isEmpty && !f.subcategories.contains(p.subcategory ?? "") { return false }
        if dim != .orientation && !f.orientations.isEmpty && !f.orientations.contains(p.orientation) { return false }
        if dim != .sourceFormat && !f.sourceFormats.isEmpty && !f.sourceFormats.contains(p.sourceFormat) { return false }
        if dim != .camera && !f.cameras.isEmpty {
            guard let cam = p.cameraBody, f.cameras.contains(cam) else { return false }
        }
        if dim != .curation && !f.curatedStatuses.isEmpty && !f.curatedStatuses.contains(p.curatedStatus) { return false }
        if dim != .grading && !f.gradingStyles.isEmpty {
            guard let gs = p.gradingStyle, f.gradingStyles.contains(gs) else { return false }
        }
        if dim != .vibe && !f.vibes.isEmpty {
            let photoVibes = Set(p.vibeList)
            if f.vibeMode == .union {
                if f.vibes.isDisjoint(with: photoVibes) { return false }
            } else {
                if !f.vibes.isSubset(of: photoVibes) { return false }
            }
        }
        if dim != .time && !f.timesOfDay.isEmpty {
            guard let td = p.timeOfDay, f.timesOfDay.contains(td) else { return false }
        }
        if dim != .setting && !f.settings.isEmpty {
            guard let s = p.setting, f.settings.contains(s) else { return false }
        }
        if dim != .exposure && !f.exposures.isEmpty {
            guard let e = p.exposure, f.exposures.contains(e) else { return false }
        }
        if dim != .depth && !f.depths.isEmpty {
            guard let d = p.depth, f.depths.contains(d) else { return false }
        }
        if dim != .composition && !f.compositions.isEmpty {
            guard let c = p.compositionTechnique, f.compositions.contains(c) else { return false }
        }
        if dim != .analysis, let v = f.analysisStatus {
            if v == "analyzed" && !p.isAnalyzed { return false }
            if v == "pending" && p.isAnalyzed { return false }
        }
        // New filters
        if dim != .location && !f.locations.isEmpty {
            guard let loc = p.locationName, f.locations.contains(loc) else { return false }
        }
        if dim != .style && !f.styles.isEmpty {
            guard let s = p.styleLabel, f.styles.contains(s) else { return false }
        }
        if dim != .aesthetic && !f.aestheticBuckets.isEmpty {
            guard let b = p.aestheticBucket, f.aestheticBuckets.contains(b) else { return false }
        }
        if dim != .hasText, let ht = f.hasTextFilter {
            if ht == "yes" && !p.hasOCRText { return false }
            if ht == "no" && p.hasOCRText { return false }
        }
        if dim != .search && !f.searchText.isEmpty {
            let q = f.searchText.lowercased()
            let haystack = [p.altText, p.filename, p.folderPath, p.vibe,
                            p.locationName, p.blipCaption, p.ocrText]
                .compactMap { $0 }.joined(separator: " ").lowercased()
            if !haystack.contains(q) { return false }
        }
        return true
    }

    // MARK: - Faceted options (contextual counts)

    private func computeFacetedOptions() {
        options.categories = facet(\.category, excluding: .category)
        options.subcategories = facetOpt(\.subcategory, excluding: .subcategory)
        options.orientations = facet(\.orientation, excluding: .orientation)
        options.sourceFormats = facet(\.sourceFormat, excluding: .sourceFormat)
        options.cameras = facetOpt(\.cameraBody, excluding: .camera)
        options.curatedStatuses = facet(\.curatedStatus, excluding: .curation)
        options.gradingStyles = facetOpt(\.gradingStyle, excluding: .grading)
        options.vibes = facetVibes()
        options.timesOfDay = facetOpt(\.timeOfDay, excluding: .time)
        options.settings = facetOpt(\.setting, excluding: .setting)
        options.exposures = facetOpt(\.exposure, excluding: .exposure)
        options.depths = facetOpt(\.depth, excluding: .depth)
        options.compositions = facetOpt(\.compositionTechnique, excluding: .composition)
        // New facets
        options.locations = facetOpt(\.locationName, excluding: .location)
        options.styles = facetOpt(\.styleLabel, excluding: .style)
        options.aestheticBuckets = facetOpt(\.aestheticBucket, excluding: .aesthetic)
    }

    private func facet(_ kp: KeyPath<PhotoItem, String>, excluding: FilterDimension) -> [FacetOption] {
        var counts: [String: Int] = [:]
        for p in allPhotos where matchesFilters(p, excluding: excluding) {
            let v = p[keyPath: kp]
            if !v.isEmpty { counts[v, default: 0] += 1 }
        }
        return counts.sorted { $0.key < $1.key }.map { FacetOption(value: $0.key, count: $0.value) }
    }

    private func facetOpt(_ kp: KeyPath<PhotoItem, String?>, excluding: FilterDimension) -> [FacetOption] {
        var counts: [String: Int] = [:]
        for p in allPhotos where matchesFilters(p, excluding: excluding) {
            if let v = p[keyPath: kp], !v.isEmpty { counts[v, default: 0] += 1 }
        }
        return counts.sorted { $0.key < $1.key }.map { FacetOption(value: $0.key, count: $0.value) }
    }

    private func facetVibes() -> [FacetOption] {
        var counts: [String: Int] = [:]
        for p in allPhotos where matchesFilters(p, excluding: .vibe) {
            for v in p.vibeList { counts[v, default: 0] += 1 }
        }
        return counts.sorted { $0.key < $1.key }.map { FacetOption(value: $0.key, count: $0.value) }
    }

    // MARK: - Filter actions

    func toggleFilter(_ keyPath: WritableKeyPath<FilterState, Set<String>>, _ value: String) {
        filters.toggle(keyPath, value)
        applyFilters()
    }

    func toggleAnalysis(_ value: String) {
        filters.analysisStatus = filters.analysisStatus == value ? nil : value
        applyFilters()
    }

    func toggleHasText(_ value: String) {
        filters.hasTextFilter = filters.hasTextFilter == value ? nil : value
        applyFilters()
    }

    func setVibeMode(_ mode: QueryMode) {
        filters.vibeMode = mode
        if !filters.vibes.isEmpty { applyFilters() }
    }

    func clearFilters() {
        filters.clear()
        applyFilters()
    }

    // MARK: - Enhanced image toggle

    func toggleEnhanced() {
        showEnhanced.toggle()
    }

    func enhancedPath(for photo: PhotoItem) -> String {
        (basePath as NSString).appendingPathComponent("rendered/enhanced/jpeg/\(photo.id).jpg")
    }

    // MARK: - Fullscreen toggle

    func toggleFullscreen() {
        isFullscreen.toggle()
    }

    // MARK: - Info panel toggle

    func toggleInfoPanel() {
        showInfoPanel.toggle()
    }

    // MARK: - Location

    func setLocation(for photo: PhotoItem, name: String) {
        database.setLocation(uuid: photo.id, name: name, lat: photo.exifGPSLat, lon: photo.exifGPSLon, source: "user_manual")
        // Propagate if we have camera + date
        if let cam = photo.cameraBody, let date = photo.dateTaken {
            let propagated = database.propagateLocation(fromUUID: photo.id, locationName: name, cameraBody: cam, dateTaken: date)
            if propagated > 0 {
                print("Propagated location '\(name)' to \(propagated) nearby images")
            }
        }
        // Reload to reflect changes
        allPhotos = database.loadPhotos()
        applyFilters()
        // Re-select the same photo
        if let updated = allPhotos.first(where: { $0.id == photo.id }) {
            selectedPhoto = updated
            selectedIndex = filteredPhotos.firstIndex(of: updated) ?? selectedIndex
        }
    }

    func acceptLocation(for photo: PhotoItem) {
        database.acceptLocation(uuid: photo.id)
        allPhotos = database.loadPhotos()
        applyFilters()
        if let updated = allPhotos.first(where: { $0.id == photo.id }) {
            selectedPhoto = updated
            selectedIndex = filteredPhotos.firstIndex(of: updated) ?? selectedIndex
        }
    }

    func rejectLocation(for photo: PhotoItem) {
        database.rejectLocation(uuid: photo.id)
        allPhotos = database.loadPhotos()
        applyFilters()
        if let updated = allPhotos.first(where: { $0.id == photo.id }) {
            selectedPhoto = updated
            selectedIndex = filteredPhotos.firstIndex(of: updated) ?? selectedIndex
        }
    }

    // MARK: - Query bar chip groups

    var chipGroups: [ChipGroup] {
        var groups: [ChipGroup] = []

        func addGroup(_ id: String, _ set: Set<String>, mode: QueryMode = .union,
                      transform: (String) -> String = { $0 }) {
            if !set.isEmpty {
                groups.append(ChipGroup(id: id, chips: set.sorted().map {
                    ActiveChip(id: "\(id):\($0)", label: transform($0))
                }, mode: mode))
            }
        }

        if let a = filters.analysisStatus {
            groups.append(ChipGroup(id: "analysis", chips: [
                ActiveChip(id: "analysis:\(a)", label: a == "analyzed" ? "Analyzed" : "Not Analyzed")
            ], mode: .union))
        }
        addGroup("curation", filters.curatedStatuses, transform: { $0.capitalized })
        addGroup("category", filters.categories)
        addGroup("folder", filters.subcategories)
        addGroup("orientation", filters.orientations, transform: { $0.capitalized })
        addGroup("format", filters.sourceFormats, transform: { $0.uppercased() })
        addGroup("camera", filters.cameras)
        addGroup("grading", filters.gradingStyles)
        addGroup("vibe", filters.vibes, mode: filters.vibeMode)
        addGroup("time", filters.timesOfDay)
        addGroup("setting", filters.settings)
        addGroup("exposure", filters.exposures)
        addGroup("depth", filters.depths)
        addGroup("composition", filters.compositions)
        addGroup("location", filters.locations)
        addGroup("style", filters.styles)
        addGroup("aesthetic", filters.aestheticBuckets)
        if let ht = filters.hasTextFilter {
            groups.append(ChipGroup(id: "hasText", chips: [
                ActiveChip(id: "hasText:\(ht)", label: ht == "yes" ? "Has Text" : "No Text")
            ], mode: .union))
        }
        if !filters.searchText.isEmpty {
            groups.append(ChipGroup(id: "search", chips: [
                ActiveChip(id: "search:\(filters.searchText)", label: "\"\(filters.searchText)\"")
            ], mode: .union))
        }
        return groups
    }

    func removeChip(_ chipId: String) {
        let parts = chipId.split(separator: ":", maxSplits: 1)
        guard parts.count == 2 else { return }
        let dim = String(parts[0])
        let val = String(parts[1])
        switch dim {
        case "analysis": filters.analysisStatus = nil
        case "curation": filters.curatedStatuses.remove(val)
        case "category": filters.categories.remove(val)
        case "folder": filters.subcategories.remove(val)
        case "orientation": filters.orientations.remove(val)
        case "format": filters.sourceFormats.remove(val)
        case "camera": filters.cameras.remove(val)
        case "grading": filters.gradingStyles.remove(val)
        case "vibe": filters.vibes.remove(val)
        case "time": filters.timesOfDay.remove(val)
        case "setting": filters.settings.remove(val)
        case "exposure": filters.exposures.remove(val)
        case "depth": filters.depths.remove(val)
        case "composition": filters.compositions.remove(val)
        case "location": filters.locations.remove(val)
        case "style": filters.styles.remove(val)
        case "aesthetic": filters.aestheticBuckets.remove(val)
        case "hasText": filters.hasTextFilter = nil
        case "search": filters.searchText = ""
        default: break
        }
        applyFilters()
    }

    // MARK: - Curation

    func curate(_ photo: PhotoItem, status: String) {
        database.setCuratedStatus(uuid: photo.id, status: status)
        if let idx = allPhotos.firstIndex(where: { $0.id == photo.id }) {
            allPhotos[idx].curatedStatus = status
        }
        if let idx = filteredPhotos.firstIndex(where: { $0.id == photo.id }) {
            filteredPhotos[idx].curatedStatus = status
        }
        refreshCounts()
    }

    func keepCurrent() {
        guard let photo = selectedPhoto else { return }
        curate(photo, status: "kept")
        moveToNext()
    }

    func rejectCurrent() {
        guard let photo = selectedPhoto else { return }
        curate(photo, status: "rejected")
        moveToNext()
    }

    func selectPhoto(_ photo: PhotoItem) {
        selectedPhoto = photo
        selectedIndex = filteredPhotos.firstIndex(of: photo) ?? -1
        showEnhanced = false  // Reset enhanced toggle on photo change
    }

    func moveToNext() {
        guard !filteredPhotos.isEmpty else { return }
        let next = min(selectedIndex + 1, filteredPhotos.count - 1)
        selectedIndex = next
        selectedPhoto = filteredPhotos[next]
        showEnhanced = false
    }

    func moveToPrevious() {
        guard !filteredPhotos.isEmpty else { return }
        let prev = max(selectedIndex - 1, 0)
        selectedIndex = prev
        selectedPhoto = filteredPhotos[prev]
        showEnhanced = false
    }

    // MARK: - Images

    func thumbnailPath(for photo: PhotoItem) -> String {
        if let p = photo.thumbPath, !p.isEmpty { return p }
        return (basePath as NSString).appendingPathComponent("rendered/thumb/jpeg/\(photo.id).jpg")
    }

    func displayPath(for photo: PhotoItem) -> String {
        if let p = photo.displayPath, !p.isEmpty { return p }
        return (basePath as NSString).appendingPathComponent("rendered/display/jpeg/\(photo.id).jpg")
    }

    func currentImagePath(for photo: PhotoItem) -> String {
        if showEnhanced {
            let enhPath = enhancedPath(for: photo)
            if FileManager.default.fileExists(atPath: enhPath) {
                return enhPath
            }
        }
        return displayPath(for: photo)
    }

    func loadThumbnail(for photo: PhotoItem) -> NSImage? {
        let key = photo.id as NSString
        if let cached = thumbCache.object(forKey: key) { return cached }
        let path = thumbnailPath(for: photo)
        guard let image = NSImage(contentsOfFile: path) else { return nil }
        thumbCache.setObject(image, forKey: key)
        return image
    }
}
