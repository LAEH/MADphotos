import SwiftUI

struct DetailView: View {
    @EnvironmentObject var store: PhotoStore
    let photo: PhotoItem
    @State private var locationText: String = ""
    @FocusState private var locationFocused: Bool
    @State private var showDetails = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Hero image with zoom/pan
                ZStack(alignment: .topTrailing) {
                    ZoomableImageView(photo: photo)
                        .aspectRatio(1, contentMode: .fit)

                    // Variant picker (only when multiple variants exist)
                    VariantPicker(photo: photo)
                        .padding(8)
                }

                // ── Actions ──
                HStack(spacing: 6) {
                    // Pick (toggle: kept ↔ pending)
                    CurationActionButton(
                        icon: "checkmark.circle.fill",
                        label: "Pick",
                        activeColor: .green,
                        isActive: photo.curatedStatus == "kept"
                    ) {
                        store.curate(photo, status: photo.curatedStatus == "kept" ? "pending" : "kept")
                    }

                    // Reject (toggle: rejected ↔ pending)
                    CurationActionButton(
                        icon: "xmark.circle.fill",
                        label: "Reject",
                        activeColor: .red,
                        isActive: photo.curatedStatus == "rejected"
                    ) {
                        store.curate(photo, status: photo.curatedStatus == "rejected" ? "pending" : "rejected")
                    }

                    // Unflag (only show when flagged)
                    if photo.curatedStatus != "pending" {
                        CurationActionButton(
                            icon: "circle",
                            label: "Unflag",
                            activeColor: .secondary,
                            isActive: false
                        ) {
                            store.curate(photo, status: "pending")
                        }
                    }

                    Spacer()

                    // Navigation
                    HStack(spacing: 4) {
                        Button { store.moveToPrevious() } label: {
                            Image(systemName: "chevron.left")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)

                        if store.selectedIndex >= 0 {
                            Text("\(store.selectedIndex + 1)/\(store.filteredPhotos.count)")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }

                        Button { store.moveToNext() } label: {
                            Image(systemName: "chevron.right")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)

                Divider().padding(.horizontal, 14)

                // ── Tags ──
                VStack(alignment: .leading, spacing: 10) {
                    // Vibes (editable)
                    if !photo.vibeList.isEmpty || photo.isAnalyzed {
                        tagSection("Vibes", color: .purple) {
                            FlowLayout(spacing: 4) {
                                ForEach(photo.vibeList, id: \.self) { vibe in
                                    TagPill(label: vibe, color: .purple) {
                                        var vibes = photo.vibeList
                                        vibes.removeAll { $0 == vibe }
                                        store.updateVibes(for: photo, vibes: vibes)
                                    }
                                }
                                AddTagButton { newVibe in
                                    var vibes = photo.vibeList
                                    vibes.append(newVibe)
                                    store.updateVibes(for: photo, vibes: vibes)
                                }
                            }
                        }
                    }

                    // Scenes
                    if !photo.scenesList.isEmpty {
                        tagSection("Scenes", color: .green) {
                            FlowLayout(spacing: 4) {
                                ForEach(Array(photo.scenesList.enumerated()), id: \.offset) { _, scene in
                                    Text(scene.0)
                                        .font(.caption2)
                                        .padding(.horizontal, 7).padding(.vertical, 3)
                                        .background(Capsule().fill(Color.green.opacity(0.12)))
                                        .foregroundColor(.primary)
                                }
                            }
                        }
                    }

                    // Style
                    if let style = photo.styleLabel {
                        tagSection("Style", color: .orange) {
                            Text(style)
                                .font(.caption2)
                                .padding(.horizontal, 7).padding(.vertical, 3)
                                .background(Capsule().fill(Color.orange.opacity(0.12)))
                        }
                    }

                    // Emotions
                    if !photo.emotionList.isEmpty {
                        tagSection("Emotions", color: .pink) {
                            FlowLayout(spacing: 4) {
                                ForEach(photo.emotionList, id: \.self) { emotion in
                                    Text(emotion.capitalized)
                                        .font(.caption2)
                                        .padding(.horizontal, 7).padding(.vertical, 3)
                                        .background(Capsule().fill(Color.pink.opacity(0.12)))
                                }
                            }
                        }
                    }

                    // Analysis tags (editable inline)
                    if photo.isAnalyzed {
                        tagSection("Analysis", color: .blue) {
                            FlowLayout(spacing: 4) {
                                if let g = photo.gradingStyle {
                                    editableTag(g, label: "grading", column: "grading_style", color: .blue)
                                }
                                if let e = photo.exposure {
                                    editableTag(e, label: "exposure", column: "exposure", color: .blue)
                                }
                                if let c = photo.compositionTechnique {
                                    editableTag(c, label: "composition", column: "composition_technique", color: .blue)
                                }
                                if let d = photo.depth {
                                    editableTag(d, label: "depth", column: "depth", color: .blue)
                                }
                                if let t = photo.timeOfDay {
                                    editableTag(t, label: "time", column: "time_of_day", color: .cyan)
                                }
                                if let s = photo.setting {
                                    editableTag(s, label: "setting", column: "setting", color: .cyan)
                                }
                                if let w = photo.weather {
                                    editableTag(w, label: "weather", column: "weather", color: .cyan)
                                }
                            }
                        }
                    }

                    // Aesthetic
                    if let score = photo.aestheticScore, let stars = photo.aestheticStars {
                        HStack(spacing: 4) {
                            ForEach(0..<5) { i in
                                let starVal = Double(i) + 1.0
                                Image(systemName: stars >= starVal ? "star.fill" :
                                        (stars >= starVal - 0.5 ? "star.leadinghalf.filled" : "star"))
                                    .font(.system(size: 10))
                                    .foregroundColor(.orange)
                            }
                            Text(String(format: "%.1f", score))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }

                    // Color palette
                    if !photo.paletteColors.isEmpty {
                        HStack(spacing: 3) {
                            ForEach(Array(photo.paletteColors.enumerated()), id: \.offset) { _, nsColor in
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(Color(nsColor: nsColor))
                                    .frame(width: 22, height: 14)
                            }
                        }
                    }

                    Divider()

                    // ── Location (always visible, editable) ──
                    locationSection

                    // ── Alt text ──
                    if let alt = photo.altText, !alt.isEmpty {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("DESCRIPTION").font(.caption2).fontWeight(.bold).foregroundColor(.secondary)
                            EditableAltText(photo: photo, store: store)
                        }
                    }

                    // ── OCR ──
                    if let text = photo.ocrText, !text.isEmpty {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("DETECTED TEXT").font(.caption2).fontWeight(.bold).foregroundColor(.secondary)
                            Text(text)
                                .font(.caption).foregroundColor(.secondary)
                                .textSelection(.enabled)
                                .padding(6)
                                .background(RoundedRectangle(cornerRadius: 4).fill(Color.yellow.opacity(0.08)))
                        }
                    }

                    Divider()

                    // ── Collapsible details ──
                    Button(action: { withAnimation(.easeOut(duration: 0.15)) { showDetails.toggle() } }) {
                        HStack {
                            Text("Details")
                                .font(.caption).fontWeight(.medium)
                            Spacer()
                            Image(systemName: showDetails ? "chevron.up" : "chevron.down")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(.secondary)
                        }
                        .foregroundColor(.primary)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)

                    if showDetails {
                        VStack(alignment: .leading, spacing: 12) {
                            detailRow("File", photo.filename)
                            detailRow("Folder", photo.folderPath)
                            detailRow("Format", photo.sourceFormat.uppercased())
                            detailRow("Dimensions", photo.dimensionLabel)
                            detailRow("Size", photo.sizeLabel)
                            detailRow("Orientation", photo.orientation.capitalized)

                            if let cam = photo.cameraBody {
                                detailRow("Camera", cam)
                            }
                            if let film = photo.filmStock {
                                detailRow("Film", film)
                            }
                            if let medium = photo.medium {
                                detailRow("Medium", medium.replacingOccurrences(of: "_", with: " ").capitalized)
                            }
                            if photo.isMonochrome {
                                detailRow("Color", "Monochrome")
                            }
                            if let date = photo.dateTaken {
                                detailRow("Date", date)
                            }
                            if let lat = photo.exifGPSLat, let lon = photo.exifGPSLon {
                                detailRow("GPS", String(format: "%.4f, %.4f", lat, lon))
                            }
                            if let fc = photo.detectedFaceCount, fc > 0 {
                                detailRow("Faces", "\(fc)")
                            }
                            if let oc = photo.detectedObjectCount, oc > 0 {
                                detailRow("Objects", "\(oc)")
                            }
                            if let sharpness = photo.sharpness {
                                detailRow("Sharpness", sharpness)
                            }
                            if let rotate = photo.shouldRotate {
                                detailRow("Rotation", rotate)
                            }

                            // Semantic pops
                            if !photo.semanticPopsList.isEmpty {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("POPS").font(.caption2).fontWeight(.bold).foregroundColor(.secondary)
                                    FlowLayout(spacing: 4) {
                                        ForEach(photo.semanticPopsList) { pop in
                                            HStack(spacing: 3) {
                                                Circle().fill(Color(nsColor: pop.nsColor)).frame(width: 6, height: 6)
                                                Text(pop.object).font(.caption2)
                                            }
                                            .padding(.horizontal, 6).padding(.vertical, 2)
                                            .background(RoundedRectangle(cornerRadius: 4).fill(Color.primary.opacity(0.04)))
                                        }
                                    }
                                }
                            }

                            // Depth
                            if let near = photo.depthNearPct, let mid = photo.depthMidPct, let far = photo.depthFarPct {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("DEPTH").font(.caption2).fontWeight(.bold).foregroundColor(.secondary)
                                    HStack(spacing: 2) {
                                        depthBar("Near", pct: near, color: .blue)
                                        depthBar("Mid", pct: mid, color: .green)
                                        depthBar("Far", pct: far, color: .orange)
                                    }
                                    .frame(height: 18)
                                }
                            }

                            // BLIP caption
                            if let caption = photo.blipCaption, !caption.isEmpty {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text("CAPTION").font(.caption2).fontWeight(.bold).foregroundColor(.secondary)
                                    Text(caption).font(.caption).foregroundColor(.secondary).italic()
                                        .textSelection(.enabled)
                                }
                            }
                        }
                    }
                }
                .padding(14)
            }
        }
        .background(Color(nsColor: .controlBackgroundColor))
        .onAppear { locationText = photo.locationName ?? "" }
        .onChange(of: photo.id) { locationText = photo.locationName ?? "" }
    }

    // MARK: - Tag section header

    private func tagSection<Content: View>(_ title: String, color: Color, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.caption2).fontWeight(.bold)
                .foregroundColor(color.opacity(0.7))
            content()
        }
    }

    // MARK: - Editable analysis tag

    private func editableTag(_ value: String, label: String, column: String, color: Color) -> some View {
        TagPill(label: value, color: color) {
            store.updateLabel(for: photo, column: column, value: nil)
        }
    }

    // MARK: - Location

    @ViewBuilder
    private var locationSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("LOCATION").font(.caption2).fontWeight(.bold).foregroundColor(.secondary)

            if let name = photo.locationName, !name.isEmpty {
                HStack(spacing: 5) {
                    Image(systemName: "mappin.circle.fill")
                        .font(.system(size: 11))
                        .foregroundColor(photo.locationAccepted ? .green : .orange)
                    Text(name)
                        .font(.caption).fontWeight(.medium)
                    if let source = photo.locationSource, source != "user_manual" {
                        Text(source)
                            .font(.caption2).foregroundColor(.secondary)
                    }
                }

                if photo.locationSource == "propagated" && !photo.locationAccepted {
                    HStack(spacing: 6) {
                        Button { store.acceptLocation(for: photo) } label: {
                            HStack(spacing: 3) {
                                Image(systemName: "checkmark").font(.system(size: 9, weight: .bold))
                                Text("Accept").font(.caption2)
                            }
                            .foregroundColor(.white)
                            .padding(.horizontal, 8).padding(.vertical, 4)
                            .background(Capsule().fill(Color.green))
                        }
                        .buttonStyle(.plain)

                        Button { store.rejectLocation(for: photo) } label: {
                            HStack(spacing: 3) {
                                Image(systemName: "xmark").font(.system(size: 9, weight: .bold))
                                Text("Reject").font(.caption2)
                            }
                            .foregroundColor(.white)
                            .padding(.horizontal, 8).padding(.vertical, 4)
                            .background(Capsule().fill(Color.red))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            HStack(spacing: 4) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                TextField("Add location...", text: $locationText)
                    .textFieldStyle(.plain)
                    .font(.caption)
                    .focused($locationFocused)
                    .onSubmit {
                        if !locationText.isEmpty { store.setLocation(for: photo, name: locationText) }
                    }
                if !locationText.isEmpty {
                    Button {
                        store.setLocation(for: photo, name: locationText)
                    } label: {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 13))
                            .foregroundColor(.green)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 6).fill(Color.primary.opacity(0.04)))
        }
    }

    // MARK: - Helpers

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.caption2).foregroundColor(.secondary)
                .frame(width: 70, alignment: .trailing)
            Text(value)
                .font(.caption)
                .textSelection(.enabled)
        }
    }

    @ViewBuilder
    private func depthBar(_ label: String, pct: Double, color: Color) -> some View {
        VStack(spacing: 1) {
            GeometryReader { geo in
                RoundedRectangle(cornerRadius: 2)
                    .fill(color.opacity(0.5))
                    .frame(width: geo.size.width * CGFloat(pct))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 2).fill(color.opacity(0.1)))
            }
            Text(label).font(.system(size: 8)).foregroundColor(.secondary)
        }
    }
}

// MARK: - Tag Pill (removable)

struct TagPill: View {
    let label: String
    let color: Color
    let onRemove: () -> Void
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 3) {
            Text(label)
                .font(.caption2)
            if isHovered {
                Button(action: onRemove) {
                    Image(systemName: "xmark")
                        .font(.system(size: 7, weight: .bold))
                        .foregroundColor(color)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(Capsule().fill(color.opacity(0.12)))
        .onHover { isHovered = $0 }
    }
}

// MARK: - Add Tag Button

struct AddTagButton: View {
    let onAdd: (String) -> Void
    @State private var isAdding = false
    @State private var text = ""

    var body: some View {
        if isAdding {
            TextField("tag", text: $text, onCommit: {
                let trimmed = text.trimmingCharacters(in: .whitespaces)
                if !trimmed.isEmpty { onAdd(trimmed) }
                text = ""
                isAdding = false
            })
            .textFieldStyle(.plain)
            .font(.caption2)
            .frame(width: 70)
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(Capsule().strokeBorder(Color.purple.opacity(0.3), lineWidth: 1))
            .onExitCommand { text = ""; isAdding = false }
        } else {
            Button { isAdding = true } label: {
                Image(systemName: "plus")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 7).padding(.vertical, 4)
                    .background(Capsule().strokeBorder(Color.primary.opacity(0.12), lineWidth: 0.5))
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - Editable Alt Text

struct EditableAltText: View {
    let photo: PhotoItem
    let store: PhotoStore
    @State private var isEditing = false
    @State private var editText = ""
    @State private var isHovered = false

    var body: some View {
        if let alt = photo.altText, !alt.isEmpty {
            HStack(alignment: .top, spacing: 6) {
                if isEditing {
                    TextField("Alt text", text: $editText, onCommit: {
                        store.updateLabel(for: photo, column: "alt_text", value: editText.isEmpty ? nil : editText)
                        isEditing = false
                    })
                    .textFieldStyle(.plain)
                    .font(.caption)
                    .padding(4)
                    .background(RoundedRectangle(cornerRadius: 4).fill(Color.primary.opacity(0.05)))
                    .onExitCommand { isEditing = false }
                } else {
                    Text(alt)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .italic()
                        .textSelection(.enabled)
                    Spacer()
                    if isHovered {
                        Button {
                            editText = alt
                            isEditing = true
                        } label: {
                            Image(systemName: "pencil")
                                .font(.system(size: 9))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .onHover { isHovered = $0 }
        }
    }
}

// MARK: - MetaSection (kept for compatibility)

struct MetaSection<Content: View>: View {
    let title: String
    var icon: String? = nil
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                if let icon = icon {
                    Image(systemName: icon)
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
                Text(title.uppercased())
                    .font(.caption2).fontWeight(.bold)
                    .foregroundColor(.secondary).kerning(0.8)
            }
            content
        }
    }
}

struct MetaRow: View {
    let label: String
    let value: String?
    var body: some View {
        if let v = value, !v.isEmpty {
            HStack(alignment: .top) {
                Text(label).font(.caption).foregroundColor(.secondary)
                    .frame(width: 70, alignment: .trailing)
                Text(v).font(.caption).textSelection(.enabled)
            }
        }
    }
}

// MARK: - Curation Action Button

struct CurationActionButton: View {
    let icon: String
    let label: String
    let activeColor: Color
    let isActive: Bool
    let action: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                Text(label)
                    .font(.system(size: 12, weight: isActive ? .semibold : .regular))
            }
            .foregroundColor(isActive ? activeColor : .secondary.opacity(isHovered ? 0.8 : 0.4))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isActive ? activeColor.opacity(0.12) : isHovered ? Color.primary.opacity(0.06) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(isActive ? activeColor.opacity(0.3) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in isHovered = hovering }
    }
}

// MARK: - Variant Picker

struct VariantPicker: View {
    @EnvironmentObject var store: PhotoStore
    let photo: PhotoItem

    var body: some View {
        let variants = store.availableVariants(for: photo)
        if variants.count > 1 {
            HStack(spacing: 0) {
                ForEach(variants, id: \.self) { variant in
                    let isActive = photo.displayVariant == variant
                    Button {
                        store.setDisplayVariant(for: photo, variant: variant)
                    } label: {
                        Text(variant.uppercased())
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(isActive ? .white : .white.opacity(0.7))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(isActive ? variantColor(variant) : Color.white.opacity(0.15))
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(3)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.black.opacity(0.5))
            )
        }
    }

    private func variantColor(_ variant: String) -> Color {
        switch variant {
        case "enhanced": return .green.opacity(0.85)
        case "cropped": return .blue.opacity(0.85)
        default: return .white.opacity(0.3)
        }
    }
}

// MARK: - Flow Layout

struct FlowLayout: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal: proposal, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(proposal: proposal, subviews: subviews)
        for (idx, pos) in result.positions.enumerated() {
            subviews[idx].place(at: CGPoint(x: bounds.minX + pos.x, y: bounds.minY + pos.y), proposal: .unspecified)
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxW = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, maxX: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxW && x > 0 {
                x = 0; y += rowHeight + spacing; rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            maxX = max(maxX, x)
        }
        return (CGSize(width: maxX, height: y + rowHeight), positions)
    }
}
