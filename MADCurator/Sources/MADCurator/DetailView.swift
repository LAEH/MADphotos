import SwiftUI

struct DetailView: View {
    @EnvironmentObject var store: PhotoStore
    let photo: PhotoItem
    @State private var keepPressed = false
    @State private var rejectPressed = false
    @State private var locationText: String = ""
    @FocusState private var locationFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Hero image — shows enhanced or original based on toggle
                ZStack(alignment: .topTrailing) {
                    if let nsImage = NSImage(contentsOfFile: store.currentImagePath(for: photo)) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(maxWidth: .infinity)
                            .background(Color.black)
                    } else {
                        Rectangle()
                            .fill(Color.black)
                            .aspectRatio(photo.aspectRatio, contentMode: .fit)
                            .frame(maxWidth: .infinity)
                            .overlay(
                                VStack(spacing: 8) {
                                    Image(systemName: "photo")
                                        .font(.largeTitle)
                                        .foregroundColor(.gray.opacity(0.3))
                                    Text("No preview")
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.gray.opacity(0.4))
                                }
                            )
                    }

                    // Enhanced/Original badge
                    if photo.hasEnhancement {
                        Text(store.showEnhanced ? "ENHANCED" : "ORIGINAL")
                            .font(.system(.caption2, design: .monospaced))
                            .fontWeight(.bold)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(store.showEnhanced ? Color.green.opacity(0.85) : Color.black.opacity(0.6))
                            .foregroundColor(.white)
                            .cornerRadius(4)
                            .padding(8)
                    }
                }

                // Curation buttons
                HStack(spacing: 12) {
                    Button(action: { store.curate(photo, status: "kept") }) {
                        Label("Keep", systemImage: "checkmark.circle.fill")
                            .font(.system(.body, design: .monospaced))
                            .frame(minWidth: 80)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.green)
                    .keyboardShortcut("k", modifiers: [])
                    .scaleEffect(keepPressed ? 0.93 : 1.0)
                    .onLongPressGesture(minimumDuration: .infinity, pressing: { pressing in
                        withAnimation(.spring(response: 0.2, dampingFraction: 0.6)) {
                            keepPressed = pressing
                        }
                    }, perform: {})

                    Button(action: { store.curate(photo, status: "rejected") }) {
                        Label("Reject", systemImage: "xmark.circle.fill")
                            .font(.system(.body, design: .monospaced))
                            .frame(minWidth: 80)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                    .keyboardShortcut("r", modifiers: [])
                    .scaleEffect(rejectPressed ? 0.93 : 1.0)
                    .onLongPressGesture(minimumDuration: .infinity, pressing: { pressing in
                        withAnimation(.spring(response: 0.2, dampingFraction: 0.6)) {
                            rejectPressed = pressing
                        }
                    }, perform: {})

                    // Enhanced toggle button
                    if photo.hasEnhancement {
                        Button(action: { store.toggleEnhanced() }) {
                            Label(store.showEnhanced ? "Original" : "Enhanced",
                                  systemImage: store.showEnhanced ? "photo" : "wand.and.stars")
                                .font(.system(.caption, design: .monospaced))
                        }
                        .buttonStyle(.bordered)
                    }

                    Spacer()

                    // Status pill
                    Text(photo.curatedStatus.uppercased())
                        .font(.system(.caption2, design: .monospaced))
                        .fontWeight(.bold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(statusColor(photo.curatedStatus).opacity(0.15))
                        .foregroundColor(statusColor(photo.curatedStatus))
                        .cornerRadius(4)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)

                Divider()

                // Metadata
                if store.showInfoPanel {
                    VStack(alignment: .leading, spacing: 20) {
                        // File info
                        MetaSection(title: "File", icon: "doc") {
                            MetaRow(label: "Filename", value: photo.filename)
                            MetaRow(label: "Folder", value: photo.folderPath)
                            MetaRow(label: "Format", value: photo.sourceFormat.uppercased())
                            MetaRow(label: "Dimensions", value: photo.dimensionLabel)
                            MetaRow(label: "Ratio", value: photo.ratioLabel)
                            MetaRow(label: "Orientation", value: photo.orientation.capitalized)
                            MetaRow(label: "Size", value: photo.sizeLabel)
                        }

                        // Camera badge
                        MetaSection(title: "Camera", icon: "camera") {
                            if let body = photo.cameraBody {
                                HStack(spacing: 6) {
                                    Image(systemName: "camera.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(.secondary)
                                    Text(body)
                                        .font(.system(.caption, design: .monospaced))
                                        .fontWeight(.medium)
                                    if let film = photo.filmStock {
                                        Text("·")
                                            .foregroundColor(.secondary.opacity(0.4))
                                        Text(film)
                                            .font(.system(.caption2, design: .monospaced))
                                            .foregroundColor(.secondary)
                                    }
                                }
                                .padding(.bottom, 2)
                            }
                            MetaRow(label: "Medium", value: photo.medium?.replacingOccurrences(of: "_", with: " ").capitalized)
                            if photo.isMonochrome {
                                MetaRow(label: "Color", value: "Monochrome")
                            }
                        }

                        // EXIF Date + GPS
                        if photo.dateTaken != nil || photo.exifGPSLat != nil {
                            MetaSection(title: "EXIF", icon: "info.circle") {
                                MetaRow(label: "Date", value: photo.dateTaken)
                                if let lat = photo.exifGPSLat, let lon = photo.exifGPSLon {
                                    MetaRow(label: "GPS", value: String(format: "%.4f, %.4f", lat, lon))
                                }
                            }
                        }

                        // Location
                        locationSection

                        if photo.isAnalyzed {
                            // Alt text — quoted block style
                            if let alt = photo.altText, !alt.isEmpty {
                                HStack(alignment: .top, spacing: 8) {
                                    RoundedRectangle(cornerRadius: 1)
                                        .fill(Color.accentColor.opacity(0.4))
                                        .frame(width: 3)
                                    Text(alt)
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .italic()
                                        .textSelection(.enabled)
                                }
                                .padding(.horizontal, 4)
                            }

                            // BLIP caption (if different from alt text)
                            if let caption = photo.blipCaption, !caption.isEmpty {
                                MetaSection(title: "Caption", icon: "text.quote") {
                                    Text(caption)
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .italic()
                                        .textSelection(.enabled)
                                }
                            }

                            // Color palette pills
                            if !photo.paletteColors.isEmpty {
                                MetaSection(title: "Palette", icon: "paintpalette") {
                                    HStack(spacing: 6) {
                                        ForEach(Array(photo.paletteColors.enumerated()), id: \.offset) { _, nsColor in
                                            Circle()
                                                .fill(Color(nsColor: nsColor))
                                                .frame(width: 20, height: 20)
                                                .overlay(
                                                    Circle()
                                                        .strokeBorder(Color.primary.opacity(0.1), lineWidth: 0.5)
                                                )
                                        }
                                    }
                                }
                            }

                            // Semantic pops — colored dot + object label
                            if !photo.semanticPopsList.isEmpty {
                                MetaSection(title: "Pops", icon: "sparkle") {
                                    FlowLayout(spacing: 6) {
                                        ForEach(photo.semanticPopsList) { pop in
                                            HStack(spacing: 4) {
                                                Circle()
                                                    .fill(Color(nsColor: pop.nsColor))
                                                    .frame(width: 8, height: 8)
                                                Text(pop.object)
                                                    .font(.system(.caption2, design: .monospaced))
                                            }
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 3)
                                            .background(
                                                RoundedRectangle(cornerRadius: 4)
                                                    .fill(Color.primary.opacity(0.05))
                                            )
                                        }
                                    }
                                }
                            }

                            // Gemini analysis
                            MetaSection(title: "Analysis", icon: "eye") {
                                MetaRow(label: "Grading", value: photo.gradingStyle)
                                MetaRow(label: "Exposure", value: photo.exposure)
                                MetaRow(label: "Sharpness", value: photo.sharpness)
                                MetaRow(label: "Composition", value: photo.compositionTechnique)
                                MetaRow(label: "Depth", value: photo.depth)
                            }

                            MetaSection(title: "Environment", icon: "cloud.sun") {
                                MetaRow(label: "Time", value: photo.timeOfDay)
                                MetaRow(label: "Setting", value: photo.setting)
                                MetaRow(label: "Weather", value: photo.weather)
                                MetaRow(label: "Faces", value: photo.facesCount.map { String($0) })
                                MetaRow(label: "Rotation", value: photo.shouldRotate)
                            }

                            // Vibes as glass pills
                            if !photo.vibeList.isEmpty {
                                MetaSection(title: "Vibes", icon: "sparkles") {
                                    FlowLayout(spacing: 4) {
                                        ForEach(photo.vibeList, id: \.self) { vibe in
                                            Text(vibe)
                                                .font(.system(.caption2, design: .monospaced))
                                                .padding(.horizontal, 8)
                                                .padding(.vertical, 4)
                                                .background(
                                                    RoundedRectangle(cornerRadius: 5)
                                                        .fill(.ultraThinMaterial)
                                                        .overlay(
                                                            RoundedRectangle(cornerRadius: 5)
                                                                .strokeBorder(Color.primary.opacity(0.08), lineWidth: 0.5)
                                                        )
                                                )
                                        }
                                    }
                                }
                            }
                        } else {
                            MetaSection(title: "Analysis", icon: "eye") {
                                HStack(spacing: 6) {
                                    Image(systemName: "clock")
                                        .font(.system(size: 10))
                                        .foregroundColor(.secondary)
                                    Text("Pending Gemini analysis...")
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.secondary)
                                }
                            }
                        }

                        // --- NEW SIGNAL SECTIONS ---

                        // Aesthetic Score
                        if let score = photo.aestheticScore, let stars = photo.aestheticStars {
                            MetaSection(title: "Aesthetic", icon: "star") {
                                HStack(spacing: 4) {
                                    ForEach(0..<5) { i in
                                        let starVal = Double(i) + 1.0
                                        Image(systemName: stars >= starVal ? "star.fill" :
                                                (stars >= starVal - 0.5 ? "star.leadinghalf.filled" : "star"))
                                            .font(.system(size: 11))
                                            .foregroundColor(.orange)
                                    }
                                    Text(String(format: "%.1f", score))
                                        .font(.system(.caption2, design: .monospaced))
                                        .foregroundColor(.secondary)
                                    if let label = photo.aestheticLabel {
                                        Text("· \(label)")
                                            .font(.system(.caption2, design: .monospaced))
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }

                        // Style Classification
                        if let style = photo.styleLabel {
                            MetaSection(title: "Style", icon: "theatermasks") {
                                HStack(spacing: 6) {
                                    Text(style)
                                        .font(.system(.caption, design: .monospaced))
                                        .fontWeight(.medium)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 3)
                                        .background(
                                            RoundedRectangle(cornerRadius: 4)
                                                .fill(Color.purple.opacity(0.15))
                                        )
                                    if let conf = photo.styleConfidence {
                                        Text(String(format: "%.0f%%", conf * 100))
                                            .font(.system(.caption2, design: .monospaced))
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }

                        // Scene Classification
                        if !photo.scenesList.isEmpty {
                            MetaSection(title: "Scene", icon: "mountain.2") {
                                FlowLayout(spacing: 6) {
                                    ForEach(Array(photo.scenesList.enumerated()), id: \.offset) { _, scene in
                                        HStack(spacing: 3) {
                                            Text(scene.0)
                                                .font(.system(.caption2, design: .monospaced))
                                            Text(String(format: "%.0f%%", scene.1 * 100))
                                                .font(.system(.caption2, design: .monospaced))
                                                .foregroundColor(.secondary)
                                        }
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 3)
                                        .background(
                                            RoundedRectangle(cornerRadius: 4)
                                                .fill(Color.primary.opacity(0.05))
                                        )
                                    }
                                }
                            }
                        }

                        // Depth Estimation
                        if let near = photo.depthNearPct, let mid = photo.depthMidPct, let far = photo.depthFarPct {
                            MetaSection(title: "Depth Map", icon: "cube.transparent") {
                                HStack(spacing: 2) {
                                    depthBar("Near", pct: near, color: .blue)
                                    depthBar("Mid", pct: mid, color: .green)
                                    depthBar("Far", pct: far, color: .orange)
                                }
                                .frame(height: 20)
                                if let complexity = photo.depthComplexity {
                                    MetaRow(label: "Complexity", value: String(format: "%.2f", complexity))
                                }
                            }
                        }

                        // Enhancement Metrics
                        if photo.hasEnhancement {
                            MetaSection(title: "Enhancement", icon: "wand.and.stars") {
                                if let pre = photo.enhPreBrightness, let post = photo.enhPostBrightness {
                                    metricDelta("Brightness", pre: pre, post: post)
                                }
                                if let pre = photo.enhPreWBShift, let post = photo.enhPostWBShift {
                                    metricDelta("WB Shift", pre: pre, post: post)
                                }
                                if let pre = photo.enhPreContrast, let post = photo.enhPostContrast {
                                    metricDelta("Contrast", pre: pre, post: post)
                                }
                            }
                        }

                        // OCR Text
                        if let text = photo.ocrText, !text.isEmpty {
                            MetaSection(title: "Detected Text", icon: "text.viewfinder") {
                                HStack(alignment: .top, spacing: 8) {
                                    RoundedRectangle(cornerRadius: 1)
                                        .fill(Color.yellow.opacity(0.4))
                                        .frame(width: 3)
                                    Text(text)
                                        .font(.system(.caption, design: .monospaced))
                                        .foregroundColor(.secondary)
                                        .textSelection(.enabled)
                                }
                            }
                        }

                        // Facial Emotions
                        if let emotions = photo.emotionsSummary, !emotions.isEmpty {
                            MetaSection(title: "Emotions", icon: "face.smiling") {
                                FlowLayout(spacing: 4) {
                                    ForEach(emotions.components(separatedBy: ", "), id: \.self) { emotion in
                                        Text(emotion.capitalized)
                                            .font(.system(.caption2, design: .monospaced))
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 3)
                                            .background(
                                                RoundedRectangle(cornerRadius: 4)
                                                    .fill(Color.primary.opacity(0.05))
                                            )
                                    }
                                }
                            }
                        }

                        // Detection counts
                        if (photo.detectedObjectCount ?? 0) > 0 || (photo.detectedFaceCount ?? 0) > 0 {
                            MetaSection(title: "Detections", icon: "viewfinder") {
                                if let fc = photo.detectedFaceCount, fc > 0 {
                                    MetaRow(label: "Faces", value: "\(fc)")
                                }
                                if let oc = photo.detectedObjectCount, oc > 0 {
                                    MetaRow(label: "Objects", value: "\(oc)")
                                }
                            }
                        }
                    }
                    .padding(16)
                }
            }
        }
        .background(Color(nsColor: .controlBackgroundColor))
        .onAppear {
            locationText = photo.locationName ?? ""
        }
        .onChange(of: photo.id) {
            locationText = photo.locationName ?? ""
        }
    }

    // MARK: - Location Section

    @ViewBuilder
    private var locationSection: some View {
        MetaSection(title: "Location", icon: "mappin.and.ellipse") {
            if let name = photo.locationName, !name.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: photo.locationSource == "gps_exif" ? "location.fill" :
                            photo.locationSource == "propagated" ? "location.north.line" : "mappin")
                        .font(.system(size: 10))
                        .foregroundColor(photo.locationAccepted ? .green : .orange)
                    Text(name)
                        .font(.system(.caption, design: .monospaced))
                        .fontWeight(.medium)
                    if let conf = photo.locationConfidence {
                        Text(String(format: "%.0f%%", conf * 100))
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundColor(.secondary)
                    }
                    if let source = photo.locationSource {
                        Text("· \(source)")
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundColor(.secondary)
                    }
                }

                // Propagated suggestion: accept/reject
                if photo.locationSource == "propagated" && !photo.locationAccepted {
                    HStack(spacing: 8) {
                        Button(action: { store.acceptLocation(for: photo) }) {
                            Label("Accept", systemImage: "checkmark")
                                .font(.system(.caption2, design: .monospaced))
                        }
                        .buttonStyle(.bordered)
                        .tint(.green)

                        Button(action: { store.rejectLocation(for: photo) }) {
                            Label("Reject", systemImage: "xmark")
                                .font(.system(.caption2, design: .monospaced))
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)
                    }
                }
            }

            if let lat = photo.latitude, let lon = photo.longitude {
                MetaRow(label: "Coords", value: String(format: "%.4f, %.4f", lat, lon))
            }

            // Editable location field
            HStack(spacing: 4) {
                TextField("Add location...", text: $locationText)
                    .textFieldStyle(.plain)
                    .font(.system(.caption, design: .monospaced))
                    .focused($locationFocused)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 4)
                    .background(RoundedRectangle(cornerRadius: 4).fill(Color.primary.opacity(0.04)))
                    .onSubmit {
                        if !locationText.isEmpty {
                            store.setLocation(for: photo, name: locationText)
                        }
                    }
                Button(action: {
                    if !locationText.isEmpty {
                        store.setLocation(for: photo, name: locationText)
                    }
                }) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 14))
                        .foregroundColor(locationText.isEmpty ? .secondary.opacity(0.3) : .green)
                }
                .buttonStyle(.plain)
                .disabled(locationText.isEmpty)
            }
        }
    }

    // MARK: - Helpers

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "kept": return .green
        case "rejected": return .red
        default: return .gray
        }
    }

    @ViewBuilder
    private func depthBar(_ label: String, pct: Double, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(String(format: "%.0f%%", pct * 100))
                .font(.system(.caption2, design: .monospaced))
                .foregroundColor(.secondary)
            GeometryReader { geo in
                RoundedRectangle(cornerRadius: 2)
                    .fill(color.opacity(0.6))
                    .frame(width: geo.size.width * CGFloat(pct))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 2).fill(color.opacity(0.1)))
            }
            Text(label)
                .font(.system(.caption2, design: .monospaced))
                .foregroundColor(.secondary)
        }
    }

    @ViewBuilder
    private func metricDelta(_ label: String, pre: Double, post: Double) -> some View {
        let delta = post - pre
        let arrow = delta >= 0 ? "arrow.up" : "arrow.down"
        HStack {
            Text(label)
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.secondary)
                .frame(width: 90, alignment: .trailing)
            Text(String(format: "%.2f", pre))
                .font(.system(.caption2, design: .monospaced))
                .foregroundColor(.secondary)
            Image(systemName: "arrow.right")
                .font(.system(size: 8))
                .foregroundColor(.secondary)
            Text(String(format: "%.2f", post))
                .font(.system(.caption2, design: .monospaced))
                .fontWeight(.medium)
            Image(systemName: arrow)
                .font(.system(size: 8))
                .foregroundColor(delta >= 0 ? .green : .orange)
        }
    }
}

// MARK: - MetaSection with icon

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
                    .font(.system(.caption2, design: .monospaced))
                    .fontWeight(.bold)
                    .foregroundColor(.secondary)
                    .kerning(1)
            }
            content
        }
    }
}

struct MetaRow: View {
    let label: String
    let value: String?

    init(label: String, value: String?) {
        self.label = label
        self.value = value
    }

    var body: some View {
        if let v = value, !v.isEmpty {
            HStack(alignment: .top) {
                Text(label)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundColor(.secondary)
                    .frame(width: 90, alignment: .trailing)
                Text(v)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
            }
        }
    }
}

// Simple flow layout for vibes
struct FlowLayout: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrange(proposal: proposal, subviews: subviews)
        return result.size
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
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var maxX: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxW && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            maxX = max(maxX, x)
        }

        return (CGSize(width: maxX, height: y + rowHeight), positions)
    }
}
