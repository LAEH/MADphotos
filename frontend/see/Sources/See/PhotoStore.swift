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
    // Multi-select mode
    @Published var isSelectMode: Bool = true
    @Published var selectedPhotos: Set<String> = []
    // Grid display mode
    @Published var squareCrop: Bool = true
    // Pre-computed sidebar counts
    @Published var quickCounts: QuickCounts = QuickCounts()
    // Sort
    @Published var sortBy: SortOption = .random
    @Published var sortDescending: Bool = true

    private var thumbCache = NSCache<NSString, NSImage>()

    init(basePath: String) {
        self.basePath = basePath
        self.database = Database(basePath: basePath)
        thumbCache.countLimit = 2000
    }

    func load() {
        var photos = database.loadPhotos()
        for i in photos.indices { photos[i].prepareCache() }
        allPhotos = photos
        restorePreferences()
        applyFilters()
        refreshCounts()
    }

    // MARK: - Preferences (persist across sessions)

    func savePreferences() {
        let ud = UserDefaults.standard
        ud.set(sortBy.rawValue, forKey: "see.sortBy")
        ud.set(sortDescending, forKey: "see.sortDesc")
        ud.set(squareCrop, forKey: "see.squareCrop")
        ud.set(showInfoPanel, forKey: "see.showInfo")
        ud.set(Array(filters.curatedStatuses), forKey: "see.curatedFilter")
    }

    private func restorePreferences() {
        let ud = UserDefaults.standard
        if let raw = ud.string(forKey: "see.sortBy"),
           let opt = SortOption(rawValue: raw) {
            sortBy = opt
        } else {
            sortBy = .random
        }
        if ud.object(forKey: "see.sortDesc") != nil {
            sortDescending = ud.bool(forKey: "see.sortDesc")
        }
        if ud.object(forKey: "see.squareCrop") != nil {
            squareCrop = ud.bool(forKey: "see.squareCrop")
        }
        if ud.object(forKey: "see.showInfo") != nil {
            showInfoPanel = ud.bool(forKey: "see.showInfo")
        }
        if let arr = ud.stringArray(forKey: "see.curatedFilter") {
            filters.curatedStatuses = Set(arr)
        } else {
            filters.curatedStatuses = ["pending"]
        }
    }

    func refreshCounts() {
        curationCounts = database.curationCounts()
    }

    // MARK: - Core filter engine

    func applyFilters() {
        filteredPhotos = allPhotos.filter { matchesFilters($0) }
        sortPhotos()
        computeFacetedOptions()
        computeQuickCounts()
        if let sel = selectedPhoto, !filteredPhotos.contains(sel) {
            selectedPhoto = nil; selectedIndex = -1
        }
    }

    private func computeQuickCounts() {
        var qc = QuickCounts()
        for p in allPhotos {
            if p.hasPeople { qc.people += 1 }
            if p.hasAnimal { qc.animals += 1 }
            if !p.hasPeople && !p.hasAnimal { qc.noSubject += 1 }
            if p.isMonochrome { qc.monochrome += 1 } else { qc.color += 1 }
            if p.hasOCRText { qc.withText += 1 }
        }
        quickCounts = qc
    }

    func setSort(_ option: SortOption) {
        if sortBy == option {
            sortDescending.toggle()
        } else {
            sortBy = option
            sortDescending = true // default descending (best/most first)
        }
        sortPhotos()
    }

    private func sortPhotos() {
        let desc = sortDescending
        switch sortBy {
        case .random:
            filteredPhotos.shuffle()
        case .aesthetic:
            filteredPhotos.sort { a, b in
                let sa = a.aestheticScore ?? 0, sb = b.aestheticScore ?? 0
                return desc ? sa > sb : sa < sb
            }
        case .date:
            filteredPhotos.sort { a, b in
                let da = a.dateTaken ?? "", db = b.dateTaken ?? ""
                return desc ? da > db : da < db
            }
        case .exposure:
            // Over > Balanced > Under
            let rank: [String: Int] = ["Over": 3, "Balanced": 2, "Under": 1]
            filteredPhotos.sort { a, b in
                let sa = rank[a.exposure ?? ""] ?? 0, sb = rank[b.exposure ?? ""] ?? 0
                return desc ? sa > sb : sa < sb
            }
        case .saturation:
            filteredPhotos.sort { a, b in
                return desc ? a.paletteSaturation > b.paletteSaturation : a.paletteSaturation < b.paletteSaturation
            }
        case .depth:
            filteredPhotos.sort { a, b in
                let da = a.depthComplexity ?? 0, db = b.depthComplexity ?? 0
                return desc ? da > db : da < db
            }
        case .brightness:
            filteredPhotos.sort { a, b in
                return desc ? a.paletteBrightness > b.paletteBrightness : a.paletteBrightness < b.paletteBrightness
            }
        case .faces:
            filteredPhotos.sort { a, b in
                let fa = a.detectedFaceCount ?? 0, fb = b.detectedFaceCount ?? 0
                return desc ? fa > fb : fa < fb
            }
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
            if f.mode(for: .vibe) == .union {
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
        if dim != .weather && !f.weathers.isEmpty {
            guard let w = p.weather, f.weathers.contains(w) else { return false }
        }
        if dim != .scene && !f.scenes.isEmpty {
            var sceneEntries: [String] = []
            if let s = p.scene1, (p.scene1Score ?? 0) >= 0.3 { sceneEntries.append(s) }
            if let s = p.scene2, (p.scene2Score ?? 0) >= 0.3 { sceneEntries.append(s) }
            if let s = p.scene3, (p.scene3Score ?? 0) >= 0.3 { sceneEntries.append(s) }
            let photoScenes = Set(sceneEntries)
            if f.mode(for: .scene) == .union {
                if f.scenes.isDisjoint(with: photoScenes) { return false }
            } else {
                if !f.scenes.isSubset(of: photoScenes) { return false }
            }
        }
        if dim != .emotion && !f.emotions.isEmpty {
            let photoEmotions = Set(p.emotionList)
            if f.mode(for: .emotion) == .union {
                if f.emotions.isDisjoint(with: photoEmotions) { return false }
            } else {
                if !f.emotions.isSubset(of: photoEmotions) { return false }
            }
        }
        if dim != .medium && !f.mediums.isEmpty {
            guard let m = p.medium, f.mediums.contains(m) else { return false }
        }
        if dim != .monochrome, let mc = f.monochromeFilter {
            if mc == "yes" && !p.isMonochrome { return false }
            if mc == "no" && p.isMonochrome { return false }
        }
        if let sf = f.subjectFilter {
            if sf == "people" && !p.hasPeople { return false }
            if sf == "animal" && !p.hasAnimal { return false }
            if sf == "none" && (p.hasPeople || p.hasAnimal) { return false }
        }
        if dim != .enhancement && !f.enhancements.isEmpty {
            guard let e = p.enhancementStatus, f.enhancements.contains(e) else { return false }
        }
        if dim != .filmStock && !f.filmStocks.isEmpty {
            guard let fs = p.filmStock, f.filmStocks.contains(fs) else { return false }
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
        options.locations = facetOpt(\.locationName, excluding: .location)
        options.styles = facetOpt(\.styleLabel, excluding: .style)
        options.aestheticBuckets = facetOpt(\.aestheticBucket, excluding: .aesthetic)
        options.weathers = facetOpt(\.weather, excluding: .weather)
        options.scenes = facetScenes()
        options.emotions = facetEmotions()
        options.mediums = facetOpt(\.medium, excluding: .medium)
        options.enhancements = facetOpt(\.enhancementStatus, excluding: .enhancement)
        options.filmStocks = facetOpt(\.filmStock, excluding: .filmStock)
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

    private func facetScenes() -> [FacetOption] {
        let minConf = 0.3
        var counts: [String: Int] = [:]
        for p in allPhotos where matchesFilters(p, excluding: .scene) {
            if let s = p.scene1, !s.isEmpty, (p.scene1Score ?? 0) >= minConf { counts[s, default: 0] += 1 }
            if let s = p.scene2, !s.isEmpty, (p.scene2Score ?? 0) >= minConf { counts[s, default: 0] += 1 }
            if let s = p.scene3, !s.isEmpty, (p.scene3Score ?? 0) >= minConf { counts[s, default: 0] += 1 }
        }
        return counts.sorted { $0.key < $1.key }.map { FacetOption(value: $0.key, count: $0.value) }
    }

    private func facetEmotions() -> [FacetOption] {
        var counts: [String: Int] = [:]
        for p in allPhotos where matchesFilters(p, excluding: .emotion) {
            for e in p.emotionList { counts[e, default: 0] += 1 }
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

    func toggleMonochrome(_ value: String) {
        filters.monochromeFilter = filters.monochromeFilter == value ? nil : value
        applyFilters()
    }

    func toggleSubject(_ value: String) {
        filters.subjectFilter = filters.subjectFilter == value ? nil : value
        applyFilters()
    }

    func setMode(_ mode: QueryMode, for dim: FilterDimension) {
        filters.setMode(mode, for: dim)
        applyFilters()
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
        (basePath as NSString).appendingPathComponent("images/rendered/enhanced/jpeg/\(photo.id).jpg")
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

    // MARK: - Label editing

    func updateLabel(for photo: PhotoItem, column: String, value: String?) {
        database.updateGeminiField(uuid: photo.id, column: column, value: value)
        allPhotos = database.loadPhotos()
        applyFilters()
        if let updated = allPhotos.first(where: { $0.id == photo.id }) {
            selectedPhoto = updated
            selectedIndex = filteredPhotos.firstIndex(of: updated) ?? selectedIndex
        }
    }

    func updateVibes(for photo: PhotoItem, vibes: [String]) {
        database.updateVibes(uuid: photo.id, vibes: vibes)
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
        addGroup("vibe", filters.vibes, mode: filters.mode(for: .vibe))
        addGroup("time", filters.timesOfDay, mode: filters.mode(for: .time))
        addGroup("setting", filters.settings, mode: filters.mode(for: .setting))
        addGroup("exposure", filters.exposures, mode: filters.mode(for: .exposure))
        addGroup("depth", filters.depths, mode: filters.mode(for: .depth))
        addGroup("composition", filters.compositions, mode: filters.mode(for: .composition))
        addGroup("location", filters.locations)
        addGroup("style", filters.styles, mode: filters.mode(for: .style))
        addGroup("aesthetic", filters.aestheticBuckets)
        addGroup("weather", filters.weathers, mode: filters.mode(for: .weather))
        addGroup("scene", filters.scenes, mode: filters.mode(for: .scene))
        addGroup("emotion", filters.emotions, mode: filters.mode(for: .emotion))
        addGroup("medium", filters.mediums, transform: { $0.replacingOccurrences(of: "_", with: " ").capitalized })
        addGroup("filmStock", filters.filmStocks)
        addGroup("enhancement", filters.enhancements, transform: { $0.capitalized })
        if let mc = filters.monochromeFilter {
            groups.append(ChipGroup(id: "monochrome", chips: [
                ActiveChip(id: "monochrome:\(mc)", label: mc == "yes" ? "Monochrome" : "Color")
            ], mode: .union))
        }
        if let sf = filters.subjectFilter {
            let label = sf == "people" ? "People" : sf == "animal" ? "Animals" : "No People/Animals"
            groups.append(ChipGroup(id: "subject", chips: [
                ActiveChip(id: "subject:\(sf)", label: label)
            ], mode: .union))
        }
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
        case "weather": filters.weathers.remove(val)
        case "scene": filters.scenes.remove(val)
        case "emotion": filters.emotions.remove(val)
        case "medium": filters.mediums.remove(val)
        case "monochrome": filters.monochromeFilter = nil
        case "subject": filters.subjectFilter = nil
        case "enhancement": filters.enhancements.remove(val)
        case "filmStock": filters.filmStocks.remove(val)
        case "hasText": filters.hasTextFilter = nil
        case "search": filters.searchText = ""
        default: break
        }
        applyFilters()
    }

    // MARK: - Multi-select

    func toggleSelectMode() {
        isSelectMode.toggle()
        if !isSelectMode { selectedPhotos.removeAll() }
    }

    func togglePhotoSelection(_ photo: PhotoItem) {
        if selectedPhotos.contains(photo.id) {
            selectedPhotos.remove(photo.id)
        } else {
            selectedPhotos.insert(photo.id)
        }
    }

    func selectAll() {
        selectedPhotos = Set(filteredPhotos.map(\.id))
    }

    func deselectAll() {
        selectedPhotos.removeAll()
    }

    func batchCurate(status: String) {
        for uuid in selectedPhotos {
            database.setCuratedStatus(uuid: uuid, status: status)
            if let idx = allPhotos.firstIndex(where: { $0.id == uuid }) {
                allPhotos[idx].curatedStatus = status
            }
        }
        selectedPhotos.removeAll()
        applyFilters()
        refreshCounts()
    }

    // MARK: - Curation

    func curate(_ photo: PhotoItem, status: String) {
        database.setCuratedStatus(uuid: photo.id, status: status)
        if let idx = allPhotos.firstIndex(where: { $0.id == photo.id }) {
            allPhotos[idx].curatedStatus = status
        }
        applyFilters()
        refreshCounts()
    }

    func keepCurrent() {
        guard let photo = selectedPhoto else { return }
        curate(photo, status: photo.curatedStatus == "kept" ? "pending" : "kept")
        moveToNext()
    }

    func rejectCurrent() {
        guard let photo = selectedPhoto else { return }
        curate(photo, status: photo.curatedStatus == "rejected" ? "pending" : "rejected")
        moveToNext()
    }

    func unflagCurrent() {
        guard let photo = selectedPhoto else { return }
        curate(photo, status: "pending")
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
        (basePath as NSString).appendingPathComponent("images/rendered/thumb/jpeg/\(photo.id).jpg")
    }

    func displayPath(for photo: PhotoItem) -> String {
        (basePath as NSString).appendingPathComponent("images/rendered/display/jpeg/\(photo.id).jpg")
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
        thumbCache.object(forKey: photo.id as NSString)
    }

    func cacheThumbnail(_ image: NSImage, for photo: PhotoItem) {
        thumbCache.setObject(image, forKey: photo.id as NSString)
    }
}
