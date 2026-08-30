package com.agent_gateway.agentops.model;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import org.postgresql.util.PGobject;

@Converter(autoApply = true)
public class VectorConverter implements AttributeConverter<float[], Object> {

    @Override
    public Object convertToDatabaseColumn(float[] attribute) {
        if (attribute == null) {
            return null;
        }
        try {
            PGobject pgObject = new PGobject();
            pgObject.setType("vector");
            StringBuilder sb = new StringBuilder();
            sb.append("[");
            for (int i = 0; i < attribute.length; i++) {
                sb.append(attribute[i]);
                if (i < attribute.length - 1) {
                    sb.append(",");
                }
            }
            sb.append("]");
            pgObject.setValue(sb.toString());
            return pgObject;
        } catch (Exception e) {
            throw new RuntimeException("Error converting float[] to PG vector", e);
        }
    }

    @Override
    public float[] convertToEntityAttribute(Object dbData) {
        if (dbData == null) {
            return null;
        }
        String str = dbData.toString();
        // Remove braces if present
        if (str.startsWith("[")) {
            str = str.substring(1);
        }
        if (str.endsWith("]")) {
            str = str.substring(0, str.length() - 1);
        }
        if (str.isBlank()) {
            return new float[0];
        }
        String[] parts = str.split(",");
        float[] result = new float[parts.length];
        for (int i = 0; i < parts.length; i++) {
            result[i] = Float.parseFloat(parts[i].trim());
        }
        return result;
    }
}
